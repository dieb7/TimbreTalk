import argparse
from image import imageRecord
import serial
import xmodem
from tempfile import TemporaryFile
from os.path import splitext
import logging


def create_xmodem_padded_temp_file(contents, packet_size=128, padding_char='\xff'):
    transfer_padding = packet_size - (len(contents) % packet_size)
    for i in range(transfer_padding):
        contents += padding_char
    padded_file = TemporaryFile(mode='r+b')
    padded_file.write(contents)
    padded_file.seek(0)
    return padded_file


def get_image_content_from_file(image_path):
    ext = splitext(image_path)
    if len(ext) == 2 and ext[1] == '.bin':
        temp = open(image_path, "rb")
        contents = temp.read()
        temp.close()
        image_content = contents
    else:
        image = imageRecord()
        image.createImage(image_path)
        image_content = bytearray(image.image)
    return image_content


def expected_flash_image(contents):
    for i in range(0x100000 - len(contents)):
        contents += '\xff'
    return contents


def calculate_flash_crc(contents):
    from PyCRC.CRCCCITT import CRCCCITT
    contents = expected_flash_image(contents)
    return CRCCCITT(version='XModem').calculate(str(contents))


def calculate_app_crc(contents):
    from PyCRC.CRCCCITT import CRCCCITT
    contents = expected_flash_image(contents)
    contents = contents[0x1000:]
    return CRCCCITT(version='XModem').calculate(contents)


def get_crc_from_response(response):
    return int(response.split('CRC: ')[1], 16)


def main(args):
    parser = argparse.ArgumentParser(description='Programs an Efm32 micro using through the default serial bootloader')
    parser.add_argument('-p', '--port', help='Serial port to use', required=True)
    parser.add_argument('-b', '--baudrate', help='Serial port to use', default=115200, type=int)
    parser.add_argument('-i', '--image', help='Path to image', required=True, type=str)
    parser.add_argument('-a', '--address', help='Address to program image', default=0x0, type=int)
    parser.add_argument('-o', '--overwrite', help='Overwrite bootloader', default=True, type=int)
    parser.add_argument('-l', '--log', help='Set debug level', default=logging.NOTSET, type=str)

    args = parser.parse_args()

    logging.basicConfig(level=args.log)

    image_content = get_image_content_from_file(args.image)
    if len(image_content) == 0:
        logging.error('Failed importing image file')
        return -1

    # here we will create temporary file from the original with some padding as the xmodem module adds some characters
    # if this is not done
    padded_file = create_xmodem_padded_temp_file(image_content)

    port = serial.Serial(port=args.port, baudrate=args.baudrate, parity=serial.PARITY_NONE, bytesize=serial.EIGHTBITS, stopbits=serial.STOPBITS_ONE, timeout=1, xonxoff=0, rtscts=0, dsrdtr=0)

    def send_cmd(cmd):
        response = ''
        port.write(cmd)
        while True:
            temp = port.read(1)
            if temp == '':
                break
            response += temp
        return response

    def getc(size, timeout=1):
        return port.read(size)

    def putc(data, timeout=1):
        port.write(data)

    port_response = send_cmd('U')
    logging.debug(port_response)

    start_banner = port_response.strip()

    if 'ChipID:' not in start_banner and 'U\r\n?' != start_banner:
        logging.error('Device did not respond to auto-baud command: {}'.format(port_response))
        return -2

    port_response = send_cmd('d')
    logging.debug(port_response)
    if 'd\r\nReady' not in port_response.strip():
        logging.error('Device did not respond to auto-baud command: {}'.format(port_response))
        return -3

    logging.info("will program micro")

    xm = xmodem.XMODEM(getc, putc)

    if not xm.send(padded_file):
        logging.error('Failed while programming EFM mcu')
        return -4

    padded_file.close()

    port_response = send_cmd('v')
    actual_crc = get_crc_from_response(port_response)
    expected_crc = calculate_flash_crc(image_content)
    if actual_crc != expected_crc:
        logging.error('Crc does not match. expected: {} actual: {}'.format(expected_crc, actual_crc))
        return -5

    send_cmd('b')
    port.close()

    logging.info("Success!")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
