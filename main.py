import time

import serial
import imageio
import numpy as np
from mss import mss
from PIL import Image

STREAM_SIZE = 128
bounding_box = {'top': 200, 'left': 200, 'width': 512, 'height': 512}
sct = mss()

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


def image_to_rgb565_bytes(r, g, b):
    r = (r.astype(np.uint16) & 0xF8) << 8
    g = (g.astype(np.uint16) & 0xFC) << 3
    b = (b.astype(np.uint16) & 0xF8) >> 3
    rgb565 = r | g | b
    rgb565 = ((rgb565 & 0xFF00) >> 8) | ((rgb565 & 0x00FF) << 8)
    flattened = rgb565.flatten().tobytes()
    # num_arrs = (flattened.shape[0] * 2) // BUF_SIZE
    # for arr in np.split(flattened, num_arrs):
    #     byte_arrays.append(arr.tobytes())
    return flattened


def grab_latest_image():
    sct_img = sct.grab(bounding_box)
    img = Image.frombytes('RGB', (sct_img.width, sct_img.height), sct_img.rgb)
    img.thumbnail((STREAM_SIZE, STREAM_SIZE))
    r, g, b = np.split(np.array(img), 3, axis=2)
    return image_to_rgb565_bytes(r, g, b), img.width, img.height


def get_images(images_in: list[str]):
    images = []
    for image in images_in:
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
        images.append(image_to_rgb565_bytes(r, g, b))
    return images


def send_image(ser, data, position):
    start_x = position[0]
    start_y = position[1]
    end_x = position[2]
    end_y = position[3]
    ser.write(start_x.to_bytes(1, byteorder="little", signed=False))
    ser.write(start_y.to_bytes(1, byteorder="little", signed=False))
    ser.write(end_x.to_bytes(1, byteorder="little", signed=False))
    ser.write(end_y.to_bytes(1, byteorder="little", signed=False))
    ser.write(len(data).to_bytes(2, byteorder="little", signed=False))
    ser.read_until(b'\xAA')
    ser.read_until(b'\xAA')
    ser.write(data)


def stream_to_device(dev: str, images: list[str], positions: list[(int, int)], baud=230400):
    squares = get_images(images)
    ser = serial.Serial(baudrate=baud)
    ser.port = dev
    ser.baudrate = baud
    ser.open()
    active = True
    last_cmd = time.time()

    while active:
        print("\nDEVICE:\n", end='')
        raw_val = ser.read()
        while raw_val != b'\xFF':
            if raw_val.isascii():
                print(raw_val.decode('utf-8'), end='')
            else:
                print("0x" + raw_val.hex(), end=' ')
            raw_val = ser.read()
        cmd = ser.read()
        print("\nHOST:")
        if cmd == b'\x01':
            print(f"return num squares: {len(squares)}")
            ser.write(len(squares).to_bytes(2, byteorder="little", signed=False))
        elif cmd == b'\x02':
            img_num = int.from_bytes(ser.read(2), byteorder="little", signed=False)
            print(f"return data from square: {img_num}")
            print(time.time() - last_cmd)
            start = time.time()
            send_image(ser, squares[img_num], positions[img_num])
            print(f"Square transfer complete, took: {time.time() - start} seconds")
            last_cmd = time.time()
        elif cmd == b'\x03':
            img, width, height = grab_latest_image()
            start_x = 64 - width//2
            start_y = 64 - height//2
            end_x = start_x + width - 1
            end_y = start_y + height - 1
            send_image(ser, img, (start_x, start_y, end_x, end_y))
        elif cmd == b'\xFE':
            active = False

    print("done")


def example():
    # images = ["./log4j.png", "mc.png", "./rusty.png", "./mcmap.png"]
    images = ["./q1.png", "./q2.png", "./q3.png", "./q4.png"]
    # positions = [(0, 0, 127, 127), (0, 0, 127, 127), (0, 0, 127, 127), (0, 0, 127, 127)]
    positions = [(0, 0, 31, 31), (32, 0, 63, 31), (0, 32, 31, 63), (32, 32, 63, 63)]
    stream_to_device("COM5", images, positions)


if __name__ == '__main__':
    example()
