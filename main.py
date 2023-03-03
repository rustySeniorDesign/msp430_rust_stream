import PIL.ImagePalette
import serial
import imageio
import numpy as np

SQUARE_LEN = 16

# https://stackoverflow.com/questions/16856788/slice-2d-array-into-smaller-2d-arrays
def blockshaped(arr, nrows, ncols):
    """
    Return an array of shape (n, nrows, ncols) where
    n * nrows * ncols = arr.size

    If arr is a 2D array, the returned array should look like n subblocks with
    each subblock preserving the "physical" layout of arr.
    """
    h, w = arr.shape
    assert h % nrows == 0, f"{h} rows is not evenly divisible by {nrows}"
    assert w % ncols == 0, f"{w} cols is not evenly divisible by {ncols}"
    return (arr.reshape(h // nrows, nrows, -1, ncols)
            .swapaxes(1, 2)
            .reshape(-1, nrows, ncols))


def image_to_squares(r, g, b):
    r = (r.astype(np.uint16) & 0xF8) << 8
    g = (g.astype(np.uint16) & 0xFC) << 3
    b = (b.astype(np.uint16) & 0xF8) >> 3
    rgb565 = r | g | b
    img_rows = blockshaped(rgb565, SQUARE_LEN, SQUARE_LEN)
    squares = []
    for square in img_rows:
        sp = []
        flattened = square.flatten()
        num_arrs = (flattened.shape[0]*2) // 256
        for arr in np.split(flattened, num_arrs):
            sp.append(arr.tobytes())
        squares.append(sp)

    return squares


def stream_to_device(dev: str, image: str, baud=115200):
    img = imageio.imopen(image, "r")
    img_data = img.read()
    img_meta = img.metadata()

    if 'palette' in img_meta:
        palette = img_meta['palette']
        palette_inv = {}
        for color, index in palette.colors.items():
            palette_inv[index] = color
        to_rgb = np.vectorize(lambda x: palette_inv[x])
        r, g, b = to_rgb(image)
    else:
        r, g, b = np.split(img_data, 3, axis=2)
        r = np.squeeze(r, axis=2)
        g = np.squeeze(g, axis=2)
        b = np.squeeze(b, axis=2)

    squares = image_to_squares(r, g, b)
    ser = serial.Serial(baudrate=baud)
    ser.port = dev
    ser.baudrate = baud
    ser.open()
    active = True
    while active:
        print("DEVICE: ", end='')
        raw_val = ser.read()
        while raw_val != b'\xFF':
            if raw_val.isascii():
                print(raw_val.decode('utf-8'), end='')
            else:
                print("0x" + raw_val.hex(), end=' ')
            raw_val = ser.read()
        # ser.read_until(expected=b'\xFF')
        cmd = ser.read()
        if cmd == b'\x01':
            print(f"\nHOST: return num squares: {len(squares)}")
            # write_verified(ser, len(squares).to_bytes(2, byteorder="little", signed=False))
            ser.write(len(squares).to_bytes(2, byteorder="little", signed=False))
        elif cmd == b'\x02':
            img_num = int.from_bytes(ser.read(2), byteorder="little", signed=False)
            print(f"HOST: return data from square: {img_num}")
            data = squares[img_num]
            square_y = (img_num // (128 // SQUARE_LEN)) * SQUARE_LEN
            square_x = (img_num % (128 // SQUARE_LEN)) * SQUARE_LEN
            ser.write(square_x.to_bytes(1, byteorder="little", signed=False))
            ser.read_until(b'\xAA')
            ser.write(square_y.to_bytes(1, byteorder="little", signed=False))
            ser.read_until(b'\xAA')
            for packet in data:
                ser.write(packet)
                # for j in range(256):

            print("HOST: Square transfer complete")
        elif cmd == b'\x03':
            active = False

    print("done")


if __name__ == '__main__':
    stream_to_device("COM5", "./mc.png")
