import io
import os
import struct
import sys

import png

import garc
import lzss3

DATA_WIDTH = 64
DATA_HEIGHT = 32
ACTUAL_WIDTH = 40
ACTUAL_HEIGHT = 30

def round_channel(n):
    return (n * 255 + 15) // 31

if len(sys.argv) != 3:
    print('usage: icons.py base_dir forms.txt')

base_dir, forms_txt = sys.argv[1:]

icon_path = os.path.join(base_dir, 'romfs', 'a', '0', '9', '3')

with open(icon_path, 'rb') as icon_file:
    icons = garc.chomp(icon_file)

code_bin_path = os.path.join(base_dir, 'exefs', 'code.bin')

forms = {}
with open(forms_txt) as forms_list:
    for line in forms_list:
        id, form, form_id = line.strip().split('|')
        forms[(int(id), int(form_id))] = form

icon_map = {}
with open(code_bin_path, 'rb') as code_bin:
    code_bin.seek(0x43EAA8)

    for pokemon in range(721):
        code_bin.seek(0x43EAA8 + 0x10 * pokemon)

        (male, female, form_offset, direction_offset, form_count,
            direction_count) = struct.unpack('<HHLLHH', code_bin.read(0x10))

        id = pokemon + 1

        icon_map['{}.png'.format(id)] = male

        if female != male:
           filename = os.path.join('female', '{}.png'.format(id))
           icon_map[filename] = female

        if form_offset:
           code_bin.seek(form_offset - 0x100000)

           for form in range(form_count):
               form_icon, = struct.unpack('<H', code_bin.read(2))

               form_name = forms[(id, form + 1)]

               if form_name:
                   filename = '{}-{}.png'.format(id, form_name)
               else:
                   filename = '{}.png'.format(id)

               icon_map[filename] = form_icon

        if direction_offset:
           code_bin.seek(direction_offset - 0x100000)

           if form_count:
               assert form_count == direction_count

               for form in range(form_count):
                   form_right, = struct.unpack('<H', code_bin.read(2))

                   form_name = forms[(id, form + 1)]

                   if form_name:
                       filename = '{}-{}.png'.format(id, form_name)
                   else:
                       filename = '{}.png'.format(id)

                   if icon_map[filename] != form_right:
                       filename = os.path.join('right', filename)
                       icon_map[filename] = form_right
           else:
               assert direction_count == 2

               right, = struct.unpack('<H', code_bin.read(2))
               if right != male:
                   filename = os.path.join('right', '{}.png'.format(id))
                   icon_map[filename] = right

for filename, icon_num in icon_map.items():
    icon = lzss3.decompress_bytes(icons[icon_num][0])
    icon = io.BytesIO(icon)

    image_count, = struct.unpack('<H', icon.read(2))

    palette_length, = struct.unpack('<H', icon.read(2))
    palette = []

    for n in range(palette_length):
        palette_entry, = struct.unpack('<H', icon.read(2))
        palette.append((
            round_channel(palette_entry >> 11 & 0x1F),  # R
            round_channel(palette_entry >> 6 & 0x1F),   # G
            round_channel(palette_entry >> 1 & 0x1F),   # B
            (palette_entry & 1) * 0xFF   # A
        ))

    if palette_length <= 0x10:
        pixels = []

        for pixel_pair in range(DATA_WIDTH * DATA_HEIGHT // 2):
            pixel_pair, = icon.read(1)

            pixels.append(pixel_pair >> 4)
            pixels.append(pixel_pair & 0x0F)
    else:
        pixels = list(icon.read(DATA_WIDTH * DATA_HEIGHT))

    untiled_pixels = [
        [None for x in range(DATA_WIDTH)]
        for y in range(DATA_HEIGHT)
    ]

    for n, pixel in enumerate(pixels):
        tile_num, within_tile = divmod(n, 64)

        tile_y, tile_x = divmod(tile_num, DATA_WIDTH // 8)
        tile_x *= 8
        tile_y *= 8

        sub_x = (
            (within_tile & 0b000001) |
            (within_tile & 0b000100) >> 1 |
            (within_tile & 0b010000) >> 2
        )

        sub_y = (
            (within_tile & 0b000010) >> 1 |
            (within_tile & 0b001000) >> 2 |
            (within_tile & 0b100000) >> 3
        )

        try:
            untiled_pixels[tile_y + sub_y][tile_x + sub_x] = pixel
        except IndexError:
            print(tile_y, sub_y, tile_x, sub_x, icon_num)

    untiled_pixels = [
        [pixel for pixel in row[:ACTUAL_WIDTH]]
        for row in untiled_pixels[:ACTUAL_HEIGHT]
    ]

    if filename.startswith('right'):
        for row in untiled_pixels:
            row.reverse()

    filename = os.path.join('/tmp/icons', filename)

    with open(filename, 'wb') as png_file:
        writer = png.Writer(width=40, height=30, palette=palette)
        writer.write(png_file, untiled_pixels)
