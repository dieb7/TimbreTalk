import argparse
from image import imageRecord
import serial
import xmodem
from tempfile import TemporaryFile
from os.path import splitext
import logging


def create_xmodem_padded_temp_file(contents, packet_size=128, padding_char=b'\xff'):
    transfer_padding = packet_size - (len(contents) % packet_size)
    for i in range(transfer_padding):
        contents += bytearray(padding_char)
    padded_file = TemporaryFile(mode='r+b')
    padded_file.write(contents)
    padded_file.seek(0)
    return padded_file


def get_image_content_from_file(image_path):
    ext = splitext(image_path)
    if len(ext) == 2 and ext[1] == '.bin':
        temp = open(image_path, 'rb')
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
        contents += b'\xff'
    return contents


def calculate_flash_crc(contents):
    from PyCRC.CRCCCITT import CRCCCITT
    contents = expected_flash_image(contents)
    return CRCCCITT(version='XModem').calculate(bytes(contents))


def calculate_app_crc(contents):
    from PyCRC.CRCCCITT import CRCCCITT
    contents = expected_flash_image(contents)
    contents = contents[0x1000:]
    return CRCCCITT(version='XModem').calculate(bytes(contents))


def get_crc_from_response(response):
    crc_str = response.decode("utf-8")
    return int(crc_str.split('CRC: ')[1], 16)


class ProgrammerPort(object):
    def __init__(self, port):
        self.port = port
        self.__current_state = self.__idle_state
        self.cmd = ''
        self.response = ''
        self.original_timeout = self.port.timeout
        self.__retries = 10

    @property
    def retries(self):
        return self.__retries

    @retries.setter
    def retries(self, value):
        logging.debug('retries {}'.format(value))
        self.__retries = value

    def __idle_state(self):
        logging.debug('__idle_state')
        self.__current_state = self.__waiting_echo_state
        self.port.write(self.cmd)
        return False

    def __waiting_echo_state(self):
        logging.debug('__waiting_echo_state')
        echo = self.port.readline().strip()
        if self.cmd != echo:
            if self.cmd != b'U':  # the auto-baud command does not echo
                self.retries -= 1
                return False
        self.__current_state = self.__waiting_response_state
        return False

    def __waiting_response_state(self):
        logging.debug('__waiting_response_state')
        self.response = self.port.readline().strip()
        if self.response == b'':
            self.retries -= 1
            return False
        self.__current_state = self.__idle_state
        return True

    def send_cmd(self, cmd):
        retries = self.retries
        if self.port.timeout != self.original_timeout:
            self.port.timeout = self.original_timeout
        self.cmd = cmd
        while not self.__current_state():
            assert self.retries > 0, 'Too many retries'
        self.retries = retries

    def getc(self, size, timeout=1):
        if timeout != self.port.timeout:
            logging.debug('Changing getc timeout {}->{}'.format(self.port.timeout, timeout))
            self.port.timeout = timeout
        return self.port.read(size)

    def putc(self, data, timeout=1):
        if timeout != self.port.timeout:
            logging.debug('Changing putc timeout {}->{}'.format(self.port.timeout, timeout))
            self.port.timeout = timeout
        self.port.write(data)


def do_efm_programmming(args_port, args_baudrate, args_image, args_overwrite, args_check, args_log):
    logging.basicConfig(level=args_log)

    image_content = get_image_content_from_file(args_image)
    if len(image_content) == 0:
        logging.error('Failed importing image file')
        return -1

    # here we will create temporary file from the original with some padding as the xmodem module adds some characters
    # if this is not done
    padded_file = create_xmodem_padded_temp_file(image_content)

    port = serial.Serial(port=args_port, baudrate=args_baudrate, parity=serial.PARITY_NONE, bytesize=serial.EIGHTBITS,
                         stopbits=serial.STOPBITS_ONE, timeout=1, xonxoff=0, rtscts=0, dsrdtr=0)

    programmer = ProgrammerPort(port)

    programmer.send_cmd(b'U')
    port_response = programmer.response
    logging.debug(port_response)

    start_banner = port_response.strip()

    if b'Chip' not in start_banner and b'?' != start_banner:
        logging.error('Device did not respond to auto-baud command: {}'.format(port_response))
        return -2

    if args_overwrite:
        programmer.send_cmd(b'd')
    else:
        programmer.send_cmd(b'u')
    port_response = programmer.response
    logging.debug(port_response)
    if b'Ready' not in port_response.strip():
        logging.error('Failed sending the program command: {}'.format(port_response))
        return -3

    logging.info('will program micro')

    xm = xmodem.XMODEM(programmer.getc, programmer.putc)

    if not xm.send(padded_file):
        logging.error('Failed while programming EFM mcu')
        return -4

    padded_file.close()

    if args_check:
        programmer.retries = 1
        programmer.original_timeout = 25
        programmer.send_cmd(b'v')
        port_response = programmer.response
        actual_crc = get_crc_from_response(port_response)
        expected_crc = calculate_flash_crc(image_content)
        if actual_crc != expected_crc:
            logging.error('Crc does not match. expected: {:08X} actual: {:08X}'.format(expected_crc, actual_crc))
            return -5

    programmer.putc(b'b')
    port.close()

    logging.info('Success!')

    return 0


def main(args):
    parser = argparse.ArgumentParser(description='Programs an Efm32 micro using through the default serial bootloader')
    parser.add_argument('-p', '--port', help='Serial port to use', required=True)
    parser.add_argument('-b', '--baudrate', help='Serial port to use', default=115200, type=int)
    parser.add_argument('-i', '--image', help='Path to image', required=True, type=str)
    parser.add_argument('-a', '--address', help='Address to program image', default=0x0, type=int)
    parser.add_argument('-o', '--overwrite', help='Overwrite bootloader', action='store_true')
    parser.add_argument('-c', '--check', help='Ask bootloader to return checksum', action='store_true')
    parser.add_argument('-l', '--log', help='Set debug level', default=logging.NOTSET, type=str)

    args = parser.parse_args()

    return do_efm_programmming(args.port, args.baudrate, args.image, args.overwrite, args.check, args.log)


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
