// Outmark matrix player. Pixel rules match python/outmark/frames.py.
// Handlers only store state. loop() advances frames with millis() and matrix.draw.
// Row 0 is the walking-history edge.
// Which physical edge that is was not checked on the glass.
// A kept event must arrive before set_plant, so growth still has the old stage.
// Growth frame count matches outmark.frames.growth_frames: same stage -> 3,
// otherwise (to - from) + 4.

#include <Arduino_LED_Matrix.h>
#include <Arduino_RouterBridge.h>

static const int MODE_REST = 0;
static const int MODE_GRID = 1;
static const int MODE_PENDING = 2;
static const int MODE_ACTIVE = 3;
static const int MODE_DONE = 4;

static const int VIEW_CHART = 0;
static const int VIEW_PLANT = 1;

static const int EVENT_STARTUP = 1;
static const int EVENT_PROPOSAL = 2;
static const int EVENT_ACCEPT = 3;
static const int EVENT_EXPIRED = 4;
static const int EVENT_KEPT = 5;
static const int EVENT_NOT_KEPT = 6;
static const int EVENT_MODE = 7;

static const int PROPOSAL_FRAMES = 4;
static const int ACCEPT_FRAMES = 3;
static const int EXPIRED_FRAMES = 14;
static const int NOT_KEPT_FRAMES = 3;
static const int REVEAL_FRAMES = 13;

static const int ROWS = 8;
static const int COLS = 13;
static const int PROGRESS_ROW = 3;
static const int CENTER_COL = 6;
static const int MASK_MAX = (1 << COLS) - 1;
static const unsigned long FRAME_MS = 160;
static const unsigned long BREATHE_MS = 900;
static const unsigned long PULSE_MS = 900;

static const uint8_t DONE_PIXELS[][2] = {
    {4, 2},
    {4, 4},
    {5, 3},
    {5, 5},
    {6, 6},
};

static const uint16_t PLANT_ROWS[6][8] = {
    {0, 0, 0, 0, 0, 0, 64, 0},
    {0, 0, 0, 0, 0, 64, 160, 0},
    {0, 0, 0, 0, 64, 64, 64, 0},
    {0, 0, 0, 64, 336, 64, 64, 0},
    {0, 0, 64, 584, 64, 224, 64, 0},
    {0, 224, 336, 64, 336, 64, 64, 0},
};

static Arduino_LED_Matrix matrix;
static int mode = MODE_REST;
static int view = VIEW_CHART;
static int progress = 0;
static int plantStage = 0;
static int shownStage = 0;
static int growthFrom = 0;
static uint16_t masks[ROWS] = {0, 0, 0, 0, 0, 0, 0, 0};
static bool dirty = true;
static bool animating = false;
static int eventCode = 0;
static int lastGeneration = -1;
static int animFrame = -1;
static int breathePhase = 0;
static int pulsePhase = 1;
static unsigned long animStart = 0;
static uint8_t frame[ROWS * COLS];

void setup() {
  matrix.begin();
  matrix.setGrayscaleBits(1);
  Bridge.begin();
  Bridge.provide_safe("set_mode", set_mode);
  Bridge.provide_safe("set_progress", set_progress);
  Bridge.provide_safe("set_grid_row", set_grid_row);
  Bridge.provide_safe("set_view", set_view);
  Bridge.provide_safe("set_plant", set_plant);
  Bridge.provide_safe("set_event", set_event);
  render();
  dirty = false;
}

void loop() {
  unsigned long now = millis();
  if (animating) {
    unsigned long elapsed = now - animStart;
    unsigned long limit = static_cast<unsigned long>(frame_count(eventCode)) * FRAME_MS;
    if (elapsed >= limit) {
      animating = false;
      if (eventCode == EVENT_KEPT && view == VIEW_PLANT) {
        shownStage = plantStage;
      }
      animFrame = -1;
      dirty = true;
    } else {
      int index = static_cast<int>(elapsed / FRAME_MS);
      if (index != animFrame) {
        animFrame = index;
        dirty = true;
      }
    }
  } else if (view == VIEW_CHART && (mode == MODE_REST || mode == MODE_PENDING || mode == MODE_ACTIVE)) {
    int phase = static_cast<int>((now / PULSE_MS) % 2);
    if (phase != pulsePhase) {
      pulsePhase = phase;
      dirty = true;
    }
  } else if (view == VIEW_PLANT && (mode == MODE_REST || mode == MODE_GRID)) {
    int phase = static_cast<int>((now / BREATHE_MS) % 2);
    if (phase != breathePhase) {
      breathePhase = phase;
      dirty = true;
    }
  }

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

void set_view(int view_id) {
  if (view_id != VIEW_CHART && view_id != VIEW_PLANT) {
    return;
  }
  view = view_id;
  dirty = true;
}

void set_plant(int stage) {
  if (stage < 0 || stage > 5) {
    return;
  }
  plantStage = stage;
  if (!animating) {
    shownStage = stage;
  }
  dirty = true;
}

void set_event(int code, int generation) {
  if (code < EVENT_STARTUP || code > EVENT_MODE) {
    return;
  }
  if (generation == lastGeneration) {
    return;
  }
  lastGeneration = generation;
  growthFrom = shownStage;
  eventCode = code;
  animating = true;
  animFrame = -1;
  animStart = millis();
  dirty = true;
}

int frame_count(int code) {
  if (code == EVENT_PROPOSAL) {
    return PROPOSAL_FRAMES;
  }
  if (code == EVENT_ACCEPT) {
    return ACCEPT_FRAMES;
  }
  if (code == EVENT_EXPIRED) {
    return EXPIRED_FRAMES;
  }
  if (code == EVENT_NOT_KEPT) {
    return NOT_KEPT_FRAMES;
  }
  if (code == EVENT_KEPT && view == VIEW_PLANT) {
    return growth_count();
  }
  return REVEAL_FRAMES;
}

int growth_count() {
  int from = growthFrom;
  int to = plantStage;
  if (to < from) {
    to = from;
  }
  if (from == to) {
    return 3;
  }
  return (to - from) + 4;
}

// Turns one non-history pixel off on alternate beats. The stored chart is unchanged.
void pulse_mark() {
  if (mode == MODE_ACTIVE && progress > 0) {
    frame[PROGRESS_ROW * COLS + progress - 1] = 0;
    return;
  }
  if (mode == MODE_PENDING) {
    frame[CENTER_COL] = 0;
    return;
  }
  if (mode == MODE_REST) {
    frame[PROGRESS_ROW * COLS + CENTER_COL] = 0;
  }
}

void render() {
  if (animating) {
    paint_event(animFrame < 0 ? 0 : animFrame);
  } else {
    paint_destination();
    if (breathePhase == 1 && view == VIEW_PLANT && (mode == MODE_REST || mode == MODE_GRID)) {
      frame[0] = 1;
    }
    if (pulsePhase == 0 && view == VIEW_CHART) {
      pulse_mark();
    }
  }
  matrix.draw(frame);
}

void paint_event(int index) {
  if (eventCode == EVENT_PROPOSAL) {
    paint_proposal(index);
  } else if (eventCode == EVENT_ACCEPT) {
    paint_accept(index);
  } else if (eventCode == EVENT_EXPIRED) {
    paint_expired(index);
  } else if (eventCode == EVENT_NOT_KEPT) {
    paint_not_kept(index);
  } else if (eventCode == EVENT_KEPT && view == VIEW_PLANT) {
    paint_growth(index);
  } else {
    paint_reveal(index);
  }
}

void paint_proposal(int index) {
  if (index <= 0) {
    clear_frame();
  } else if (index < 3) {
    paint_plant(0);
  } else {
    paint_pending();
  }
}

void paint_accept(int index) {
  paint_pending();
  if (index == 1) {
    frame[PROGRESS_ROW * COLS] = 1;
  }
}

void paint_expired(int index) {
  if (index >= COLS) {
    paint_done();
    return;
  }
  clear_frame();
  for (int row = 0; row < ROWS; ++row) {
    frame[row * COLS + index] = 1;
  }
}

void paint_not_kept(int index) {
  paint_plant(plantStage);
  if (index == 1) {
    frame[COLS - 1] = 1;
  }
}

void paint_growth(int index) {
  int from = growthFrom;
  int to = plantStage;
  if (to < from) {
    to = from;
  }
  int stage = to;
  bool shimmer = false;
  if (from == to) {
    shimmer = index == 1;
  } else {
    int count = to - from;
    if (index <= 1) {
      stage = from;
    } else if (index < 2 + count) {
      stage = from + (index - 1);
    }
    shimmer = index == 2 + count;
  }
  paint_plant(stage);
  if (shimmer) {
    frame[0] = 1;
  }
}

void paint_reveal(int index) {
  int step = index;
  if (step < 0) {
    step = 0;
  }
  if (step > COLS - 1) {
    step = COLS - 1;
  }
  paint_destination();
  for (int row = 0; row < ROWS; ++row) {
    for (int column = step + 1; column < COLS; ++column) {
      frame[row * COLS + column] = 0;
    }
  }
}

void paint_destination() {
  if (view == VIEW_PLANT && (mode == MODE_REST || mode == MODE_GRID)) {
    paint_plant(plantStage);
    return;
  }
  if (view == VIEW_PLANT && mode == MODE_ACTIVE) {
    paint_plant(plantStage);
    for (int column = 0; column < progress; ++column) {
      frame[7 * COLS + column] = 1;
    }
    return;
  }
  paint_legacy();
}

void paint_legacy() {
  clear_frame();
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
    paint_pending();
  } else if (mode == MODE_DONE) {
    paint_done();
  } else {
    frame[PROGRESS_ROW * COLS + CENTER_COL] = 1;
  }
}

void paint_plant(int stage) {
  clear_frame();
  if (stage < 0 || stage > 5) {
    return;
  }
  for (int row = 0; row < ROWS; ++row) {
    uint16_t mask = PLANT_ROWS[stage][row];
    for (int column = 0; column < COLS; ++column) {
      if ((mask & (1 << column)) != 0) {
        frame[row * COLS + column] = 1;
      }
    }
  }
}

void paint_pending() {
  clear_frame();
  for (int row = 0; row < ROWS; ++row) {
    frame[row * COLS + CENTER_COL] = 1;
  }
}

void paint_done() {
  clear_frame();
  for (unsigned int index = 0; index < sizeof(DONE_PIXELS) / sizeof(DONE_PIXELS[0]); ++index) {
    frame[DONE_PIXELS[index][0] * COLS + DONE_PIXELS[index][1]] = 1;
  }
}

void clear_frame() {
  for (int index = 0; index < ROWS * COLS; ++index) {
    frame[index] = 0;
  }
}
