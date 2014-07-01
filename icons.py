import io
import os
import struct
import sys

import png
import yaml

import garc
import lzss3

class Icon:
    """An icon."""

    # The size the image is stored as, versus its actual intended dimensions.
    # Each icon has a footer at 0x1000 that contains this info, but it's always
    # the same.
    raw_width = 64
    raw_height = 32

    width = 40
    height = 30

    def __init__(self, data, index):
        """Take raw icon data and parse it into an icon."""

        self.data = io.BytesIO(data)
        self.index = index
        self.flipped = False

        # The first two bytes are always 0x02 0x00 and I don't know what
        # they're supposed to be
        self.data.seek(2)

        self.read_palette()
        self.read_image()
        self.untile()
        self.crop()

    def __eq__(self, other):
        """Determine whether two icons are equal by checking if they were
        parsed from the same raw icon.
        """

        return self.index == other.index

    def read_palette(self):
        """Read the image's palette."""

        (self.palette_length,) = struct.unpack('<H', self.data.read(2))
        self.palette = []

        for n in range(self.palette_length):
            # Each palette entry is sixteen bits: RRRRRGGGGGBBBBBA
            (palette_entry,) = struct.unpack('<H', self.data.read(2))

            self.palette.append((
                round_channel(palette_entry >> 11 & 0x1F),  # R
                round_channel(palette_entry >> 6 & 0x1F),   # G
                round_channel(palette_entry >> 1 & 0x1F),   # B
                (palette_entry & 1) * 0xFF                  # A
            ))

    def read_image(self):
        """Read the image."""

        if self.palette_length <= 0x10:
            # If the palette is short enough, two pixels get stuffed into each
            # byte
            self.raw_pixels = []
            image_length = self.raw_width * self.raw_height // 2

            for pixel_pair in self.data.read(image_length):
                self.raw_pixels.append(pixel_pair >> 4)
                self.raw_pixels.append(pixel_pair & 0x0F)
        else:
            # The palette's too long to be clever, so one byte equals one pixel
            image_length = self.raw_width * self.raw_height
            self.raw_pixels = list(self.data.read(image_length))

    def untile(self):
        """Unscramble pixels into plain old rows.

        The pixels are arranged in 8×8 tiles, and each tile is a third-
        iteration Z-order curve.
        """

        # Build a list of rows.  Each row is a list of pixels; each pixel is
        # its palette index.
        self.pixels = [
            [None for x in range(self.raw_width)]
            for y in range(self.raw_height)
        ]

        for n, pixel in enumerate(self.raw_pixels):
            # Find the coordinates of the top-left corner of the current tile.
            # n.b. The image is eight tiles wide, and each tile is 8×8 pixels.
            tile_num = n // 64
            tile_y = tile_num // 8 * 8
            tile_x = tile_num % 8 * 8

            # Determine the pixel's coordinates within the tile
            # http://en.wikipedia.org/wiki/Z-order_curve#Coordinate_values
            within_tile = n % 64

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

            # Add up the pixel's coordinates within the whole image
            x = tile_x + sub_x
            y = tile_y + sub_y

            self.pixels[y][x] = pixel

    def crop(self):
        """Crop the image to its actual, intended size."""

        self.pixels = [row[:self.width] for row in self.pixels[:self.height]]

    def flip(self):
        """Mirror the image so that it faces the other direction, unless it's
        already been flipped.

        Nothing about the icon itself indicates whether or not it will need to
        be flipped, so this method is called once we know whether it's a right-
        facing icon.  Icons for named default forms will be saved twice, hence
        the need to make sure this method only flips the image the first time.
        """

        if not self.flipped:
            for row in self.pixels:
                row.reverse()

            self.flipped = True

    def save(self, filename):
        """Save the image."""

        with open(filename, 'wb') as png_file:
            writer = png.Writer(width=self.width, height=self.height,
                                palette=self.palette)
            writer.write(png_file, self.pixels)

def round_channel(n):
    """Scale and round a five-bit colour channel to eight bits."""

    # Equivalent to round(n * 255 / 31)
    return (n * 255 + 15) // 31

def map_icons(pokemon, all_icons, code_bin):
    """Out of all the icons, find and return icons for the given Pokémon.

    The icons in a/0/9/3 are in no particular order, but there's a huge array
    at 0x43EA98 in exefs/code.bin mapping each Pokémon to all its icons
    (including gender differences, forms, and right-facing icons for
    asymmetrical Pokémon).
    """

    code_bin.seek(0x43EA98 + 0x10 * pokemon)

    (index, female_index, form_index_offset, right_index_offset, form_count,
        right_count) = struct.unpack('<HHLLHH', code_bin.read(0x10))

    # Side note: "default" and "female" makes me wince but the default icon is
    # only necessarily the male icon when the female icon is different
    icons = {'default': all_icons[index], 'female': all_icons[female_index]}

    # Pokémon with multiple forms and/or separate right-facing icons have
    # offsets pointing to arrays containing those icons' indices
    if form_count:
        # code.bin is loaded at 0x100000 in RAM, so we need to subtract
        # 0x100000 to get an offset within the file
        code_bin.seek(form_index_offset - 0x100000)
        icons['forms'] = [
            all_icons[index] for (index,) in
            struct.iter_unpack('<H', code_bin.read(form_count * 2))
        ]

    if right_count:
        code_bin.seek(right_index_offset - 0x100000)
        icons['right'] = [
            all_icons[index] for (index,) in
            struct.iter_unpack('<H', code_bin.read(right_count * 2))
        ]

    return icons

def filename(directory, pokemon, form=None, female=False, right=False):
    """Build a filename for an icon given the attributes of the Pokémon it
    depicts.
    """

    if form is None:
        filename = '{}.png'.format(pokemon)
    else:
        filename = '{}-{}.png'.format(pokemon, form)

    if female:
        filename = os.path.join('female', filename)

    if right:
        filename = os.path.join('right', filename)

    return os.path.join(directory, filename)

def save_icons(icons, output_dir, pokemon, form_names):
    """Save all the given icons, using the given Pokémon number and form names
    to determine filenames.
    """

    # Save the default icon
    icons['default'].save(filename(output_dir, pokemon))

    # Save the female icon, if it's separate
    if icons['female'] != icons['default']:
        icons['female'].save(filename(output_dir, pokemon, female=True))

    # Save icons for all forms, if the Pokémon has multiple forms
    if 'forms' in icons:
        # Make sure we got exactly enough names for this Pokémon's forms
        name_count = 0 if form_names is None else len(form_names)
        form_count = len(icons['forms'])

        if name_count != form_count:
            raise ValueError('Pokémon #{}: got {} names for {} forms'
                             .format(pokemon, name_count, form_count))

        for form, icon in zip(form_names, icons['forms']):
            # We've already saved the default form as ###.png, but we want to
            # save it again as ###-formname.png as long as it has a name
            if form is not None:
                icon.save(filename(output_dir, pokemon, form=form))

    # Save right-facing icons for asymmetrical Pokémon
    if 'right' in icons:
        # Save the first right-facing icon if it's separate.  For Pokémon with
        # multiple forms, this will be the default form; for other Pokémon, the
        # same icon is specified twice for unknown reasons so we just save one.
        if icons['right'][0] != icons['default']:
            icon = icons['right'][0]
            icon.flip()
            icon.save(filename(output_dir, pokemon, right=True))

        # Deal with forms.  If even one of a Pokémon's forms is asymmetrical,
        # then *all* its forms have right-facing icons specified, but they'll
        # be the same icon as before for symmetrical forms.

        # Also, once again, we've already saved the default form as
        # right/###.png, but we also want right/###-formname.png if applicable.
        if 'forms' in icons:
            icon_zip = zip(form_names, icons['right'], icons['forms'])

            for (form, right_icon, left_icon) in icon_zip:
                if form is not None and right_icon != left_icon:
                    right_icon.flip()
                    right_icon.save(filename(output_dir, pokemon, form=form,
                                             right=True))


# Parse args
if len(sys.argv) != 3:
    print('usage: icons.py rom_dir output_dir')
    exit()

rom_dir, output_dir = sys.argv[1:]

# Create the necessary directory structure
os.makedirs(os.path.join(output_dir, 'female'), exist_ok=True)
os.makedirs(os.path.join(output_dir, 'right'), exist_ok=True)

# Parse the icons
icon_path = os.path.join(rom_dir, 'romfs', 'a', '0', '9', '3')

with open(icon_path, 'rb') as icon_file:
    icons = garc.chomp(icon_file)

icons = [
    Icon(lzss3.decompress_bytes(icon), index)
    for index, [icon] in enumerate(icons)
]

# Map icons to Pokémon and save them all
code_bin_path = os.path.join(rom_dir, 'exefs', 'code.bin')

with open('forms.yaml') as form_list:
    form_names = yaml.load(form_list)

with open(code_bin_path, 'rb') as code_bin:
    for pokemon in range(1, 722):
        pokemon_icons = map_icons(pokemon, icons, code_bin)
        save_icons(pokemon_icons, output_dir, pokemon, form_names.get(pokemon))

# Save the egg icon
icons[-1].save(filename(output_dir, 'egg'))
