// Outmark matrix. Mode numbers and pixel rules match python/outmark/display.py.
// Provide handlers only store state. loop() redraws and does not wait on the timer.

#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>

static const int MODE_REST = 0;
static const int MODE_GRID = 1;
static const int MODE_PENDING = 2;
static const int MODE_ACTIVE = 3;
static const int MODE_DONE = 4;

static const int ROWS = 8;
static const int COLS = 13;
static const int PROGRESS_ROW = 3;
static const int CENTER_COL = 6;
static const int MASK_MAX = (1 << COLS) - 1;

// A small check, distinct from the center column and the progress row.
static const uint8_t DONE_PIXELS[][2] = {
    {4, 2},
    {4, 4},
    {5, 3},
    {5, 5},
    {6, 6},
};

static Arduino_LED_Matrix matrix;
static int mode = MODE_REST;
static int progress = 0;
static uint16_t masks[ROWS] = {0, 0, 0, 0, 0, 0, 0, 0};
static bool dirty = true;
static uint8_t frame[ROWS * COLS];

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(1);
  Bridge.begin();
  Bridge.provide_safe("set_mode", set_mode);
  Bridge.provide_safe("set_progress", set_progress);
  Bridge.provide_safe("set_grid_row", set_grid_row);
  render();
  dirty = false;
}

void loop() {
  if (!dirty) {
    return;
  }
  render();
  dirty = false;
}

void set_mode(int mode_id) {
  if (mode_id < MODE_REST || mode_id > MODE_DONE) {
    return;
  }
  mode = mode_id;
  dirty = true;
}

void set_progress(int segments) {
  if (segments < 0 || segments > COLS) {
    return;
  }
  progress = segments;
  dirty = true;
}

void set_grid_row(int row, int mask) {
  if (row < 0 || row >= ROWS || mask < 0 || mask > MASK_MAX) {
    return;
  }
  masks[row] = static_cast<uint16_t>(mask);
  dirty = true;
}

void render() {
  for (int index = 0; index < ROWS * COLS; ++index) {
    frame[index] = 0;
  }

  if (mode == MODE_GRID) {
    for (int row = 0; row < ROWS; ++row) {
      for (int column = 0; column < COLS; ++column) {
        if ((masks[row] & (1 << column)) != 0) {
          frame[row * COLS + column] = 1;
        }
      }
    }
  } else if (mode == MODE_ACTIVE) {
    for (int column = 0; column < progress; ++column) {
      frame[PROGRESS_ROW * COLS + column] = 1;
    }
  } else if (mode == MODE_PENDING) {
    for (int row = 0; row < ROWS; ++row) {
      frame[row * COLS + CENTER_COL] = 1;
    }
  } else if (mode == MODE_DONE) {
    for (unsigned int index = 0; index < sizeof(DONE_PIXELS) / sizeof(DONE_PIXELS[0]); ++index) {
      frame[DONE_PIXELS[index][0] * COLS + DONE_PIXELS[index][1]] = 1;
    }
  } else {
    frame[PROGRESS_ROW * COLS + CENTER_COL] = 1;
  }

  matrix.draw(frame);
}
