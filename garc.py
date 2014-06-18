import struct
import subprocess
import sys

import lzss3

def chomp(garc_file):
    # CRAG header
    (magic, header_size, byte_order, unknown, chunks, data_offset, garc_length,
        last_length) = struct.unpack('<4sLHHLLLL', garc_file.read(28))

    assert magic == b'CRAG'
    assert header_size == 0x1C
    assert byte_order == 0xFEFF
    assert unknown == 0x0400
    assert chunks == 4

    # FATO
    magic, fato_size, fato_count, padding = struct.unpack('<4sLHH',
        garc_file.read(12))

    assert magic == b'OTAF'
    assert padding == 0xFFFF

    fatb_offsets = list(struct.unpack('<{}L'.format(fato_count),
        garc_file.read(4 * fato_count)))

    # FATB
    fatb_start = header_size + fato_size
    assert garc_file.tell() == fatb_start

    magic, fatb_length, file_count = struct.unpack('<4s2L', garc_file.read(12))

    assert magic == b'BTAF'

    file_meta = []

    for offset in fatb_offsets:
        garc_file.seek(fatb_start + offset + 0xC)

        file_meta.append([])
        bits, = struct.unpack('<L', garc_file.read(4))

        while bits:
            if bits & 1:
                file_meta[-1].append(struct.unpack('<3L', garc_file.read(12)))

            bits >>= 1

    # FIMB
    garc_file.seek(fatb_start + fatb_length)

    magic, fimb_header_length, fimb_length = struct.unpack('<4s2L',
        garc_file.read(12))

    assert magic == b'BMIF'
    assert fimb_header_length == 0xC

    files = []

    for file_ in file_meta:
        files.append([])

        for start, end, length in file_:
            garc_file.seek(data_offset + start)
            files[-1].append(garc_file.read(length))

    return files

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('usage: garc.py garc_file dump_file')

    garc_filename, dump_filename = sys.argv[1:]

    if garc_filename.endswith('a/0/0/7'):
        exit(1)

    with open(garc_filename, 'rb') as garc_file:
        garc = chomp(garc_file)

    with open(dump_filename, 'w') as dump_file:
        for file_num, file_ in enumerate(garc):
            for subfile_num, subfile in enumerate(file_):
                # if not file_num == subfile_num == 0:
                #     dump_file.write('\n\n')

                lzssed = False

                if subfile and subfile[0] in [0x10, 0x11]:
                    try:
                        subfile = lzss3.decompress_bytes(subfile)
                        lzssed = True
                    except:
                        pass

                print(' '.join('{:02X}'.format(b) for b in subfile), file=dump_file)

                # dump_file.write('### FILE {}.{}{}\n'.format(file_num,
                #     subfile_num, ' (LZSS decompressed)' if lzssed else ''))
                # dump_file.flush()

                # with subprocess.Popen(['xxd'], stdin=subprocess.PIPE,
                #   stdout=dump_file) as xxd:
                #     xxd.communicate(subfile)

                # dump_file.flush()
