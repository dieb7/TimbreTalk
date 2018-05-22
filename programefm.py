import argparse
from image import imageRecord
import serial
import xmodem
from tempfile import TemporaryFile


def create_xmodem_padded_temp_file(contents, packet_size=128, padding_char='\xff'):
    transfer_padding = packet_size - (len(contents) % packet_size)
    for i in range(transfer_padding):
        contents += padding_char
    padded_file = TemporaryFile(mode='r+b')
    padded_file.write(contents)
    padded_file.seek(0)
    return padded_file


def main(args):
    parser = argparse.ArgumentParser(description='Programs an Efm32 micro using through the default serial bootloader')
    parser.add_argument('-p', '--port', help='Serial port to use', required=True)
    parser.add_argument('-i', '--image', help='Path to image', required=True, type=str)
    parser.add_argument('-a', '--address', help='Address to program image', default=0x0, type=int)
    parser.add_argument('-o', '--overwrite', help='Overwrite bootloader', default=True, type=int)

    args = parser.parse_args()

    port = serial.Serial(port=args.port, baudrate=115200, parity=serial.PARITY_NONE, bytesize=serial.EIGHTBITS, stopbits=serial.STOPBITS_ONE, timeout=1, xonxoff=0, rtscts=0, dsrdtr=0)

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
    print(port_response)

    # start_banner_fields = port_response.strip().split(' ')
    #
    # if len(start_banner_fields) != 3 or start_banner_fields[1] != 'ChipID:':
    #     return -1
    #
    # print('Programing MCU with ID: {}'.format(start_banner_fields[2]))

    port_response = send_cmd('d')
    print(port_response)
    if 'd\r\nReady\r\n' not in port_response.strip():
        return -255

    # here we will create temporary file from the original with some padding
    image = imageRecord()
    image.createImage(args.image)
    padded_file = create_xmodem_padded_temp_file(bytearray(image.image))

    print("will program micro")

    xm = xmodem.XMODEM(getc, putc)

    print(xm.send(padded_file))

    padded_file.close()

    port_response = send_cmd('v')
    print(port_response)
    port_response = send_cmd('c')
    print(port_response)
    port_response = send_cmd('n')
    print(port_response)
    port_response = send_cmd('m')
    print(port_response)

    port.close()

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
