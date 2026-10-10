# Outmark — Your Offline Life, Made Visible

**Tagline:** Make a promise. Step away. Leave a mark.

## 1. Project Overview

Outmark is a self-discipline companion built using the Arduino UNO Q. It encourages users to take meaningful breaks from their screens and spend time outdoors.

The device does not monitor users, track their location, or attempt to verify their behavior. Instead, it helps users make realistic commitments, follow through on them, and reflect honestly on their actions.

Every time users report completing an activity, Outmark updates a visual record on its built-in 8 × 13 LED matrix.

Over 13 days, the matrix becomes a small physical representation of the user's offline habits.

An open-weight language model running locally on the UNO Q generates personalized activities and adapts suggestions based on the user's recorded history.

**The central idea:** Discipline cannot be installed in someone by an application. But an application can help someone make their intentions visible.

## 2. The Problem

People frequently intend to take breaks from their screens but end up scrolling social media, watching videos, or returning to work without doing anything meaningful.

Most digital habit trackers rely on notifications, streaks, points, and dashboards that require even more screen time.

Outmark takes a different approach.

- Users choose their own commitments.
- The device offers achievable, personalized outdoor activities.
- Users report their results honestly.
- Their completed activities create a lasting visual pattern.
- Missing a day does not erase their previous progress.

The project focuses on self-accountability rather than surveillance or punishment.

## 3. Target Users

Outmark is designed for students, developers, remote workers, and other people who spend long periods at a desk.

Example use cases include:

- A student taking a 10-minute outdoor break between study sessions.
- A developer stepping away from their computer after a long coding session.
- Someone trying to spend more time observing nature.
- Someone wanting to make their daily routine less repetitive.

## 4. Core User Journey

### Step 1: Make a commitment

The user opens Outmark's local webpage on an existing phone or computer.

They choose:

- Duration: 5, 10, or 15 minutes.
- Activity category.
- Optional mood or preference.

Outmark generates one practical outdoor challenge.

Example:

**Your commitment:** Take a 10-minute break.

**Your challenge:** Walk along a familiar route. Notice three different patterns around you and find something you have never paid attention to before.

The user accepts the commitment and starts the session.

### Step 2: The physical device changes state

The UNO Q displays a simple active-session pattern on its LED matrix.

The board remains powered on the desk while the user steps away. The timer continues independently of the browser.

The display shows progress visually; it does not try to display a countdown in text.

### Step 3: Return and reflect

When the session ends, the user returns to the webpage.

They choose one of two options:

- I kept my commitment.
- I did not complete it.

If they completed the activity, they can record one short observation about what they noticed or experienced.

The application records the response without claiming that it independently verified the activity.

### Step 4: Leave a mark

When the user reports success, Outmark updates the corresponding cell in its 13-day activity grid.

The matrix returns to the history view.

A missed commitment does not delete existing entries, reset progress, or cause a virtual character to die.

### Step 5: Improve future suggestions

The next time the user starts a session, the local AI can examine their recent activities and reflections.

If they repeatedly choose the same activity, it can suggest an alternative. If they have not explored a particular category recently, it can recommend that category.

The user remains in control of whether to follow the suggestion.

---

## 5. The Most Important Feature: The 13-Day Matrix

The UNO Q has an 8-row by 13-column monochrome blue LED matrix.

Outmark uses its dimensions directly.

- Each of the 8 rows represents an activity category.
- Each of the 13 columns represents one day.
- An illuminated pixel represents a completed, self-reported activity in that category on that day.
- An unlit pixel means no completed activity has been recorded for that category and day.

The category names and dates appear on the webpage, not on the matrix. The physical display only needs to show the pattern.

### The eight activity categories

1. Walking and movement.
2. Nature observation.
3. Quiet outdoor time.
4. Social connection.
5. Outdoor care or helping.
6. Exploring a new place.
7. Creative observation.
8. Other offline experiences.

### Example

Suppose the user takes a walk on Monday, observes nature on Tuesday, and spends quiet time outside on Wednesday.

The relevant pixels in the corresponding rows and day columns light up.

After several days, the display contains a pattern showing the range of activities the user has reported completing.

If the user repeatedly walks but never tries another activity, the grid makes that pattern visible. The AI can then suggest something different.

Multiple activities in the same category on one day still produce one illuminated cell. Detailed counts and notes remain available in the webpage's history.

### Why this display works

The matrix is small and monochrome. It is not suitable for paragraphs, detailed plant illustrations, photographs, or complex multicolor scenes.

Outmark therefore uses:

- A binary activity grid for history.
- A simple 13-segment progress bar during a break.
- A small checkmark-like pattern when the timer ends.
- Optional simple icons for different interface states.

Only one display mode is shown at a time.

This gives the onboard matrix a functional purpose rather than treating it as decoration.

---

## 6. Hardware Architecture

The project requires only the Arduino UNO Q and the user's existing phone or computer for interacting with the webpage and developing the software.

### Qualcomm Linux processor

Runs:

- Python application.
- Local web server.
- Open-weight language model and inference runtime.
- Session timer and state management.
- Local storage for activity history.
- Logic for converting the activity history into eight 13-bit row masks.

### STM32 microcontroller

Runs the Arduino sketch responsible for:

- Initializing the LED matrix.
- Drawing the 104-pixel history grid.
- Rendering the activity progress bar.
- Showing the completed-session indicator.
- Receiving display updates from the Linux application through Arduino Bridge.

The Linux application sends compact state updates rather than asking the microcontroller to run the language model.

### LED matrix

The matrix is the physical interface and visual record.

### RGB LEDs

Use the onboard RGB LEDs only for optional status feedback, such as an active session or a completed session. These are supplementary; the MVP should remain useful using the matrix alone.

### No additional hardware

The MVP does not need a camera, microphone, GPS module, external screen, soil sensor, speaker, or battery.

Use the existing computer or phone to access the local interface. The device itself remains on the desk.

---

## 7. Software Stack

| Component | Recommended technology |
|---|---|
| Integrated development | Arduino App Lab |
| Linux-side application | Python |
| Web backend | Flask |
| Frontend | HTML, CSS, and JavaScript |
| Local AI | llama.cpp-compatible local inference runtime |
| Open-weight model | Qwen2.5-0.5B-Instruct, Q4_K_M GGUF |
| Local storage | JSON file |
| MCU programming | Arduino C++ sketch |
| Matrix graphics | Arduino_LED_Matrix library |
| Linux–MCU communication | Arduino Bridge |
| Timer | Python monotonic clock plus persisted session timestamps |

Use JSON for the MVP because it is simple to inspect, edit, and debug. A database is unnecessary for this short build.

## 8. Open-Weight AI Strategy

Use **Qwen2.5-0.5B-Instruct in Q4_K_M GGUF format** as the initial model candidate.

The model repository publishes quantized GGUF weights under the Apache 2.0 license. The Q4_K_M file is approximately 491 MB. <https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF>

The UNO Q's 4 GB RAM variant is a reasonable platform for experimenting with this small model, but actual inference speed and memory use must be checked on the board.

### Why use a compact model?

Outmark has a narrow task. It does not require a general-purpose chatbot.

It only needs to:

1. Generate short outdoor activities.
2. Adapt suggestions to recent history.
3. Interpret optional reflections.
4. Avoid repetitive recommendations.

The model can be constrained to produce short structured output.

### Practical model setup

Start with Arduino's existing local LLM chatbot example on the UNO Q:

<https://projecthub.arduino.cc/robuinlabs/local-llm-ai-chatbot-on-arduino-uno-q-043aa9>

Reuse its working local inference endpoint if available, then replace the generic chatbot prompt with Outmark's activity-generation prompt.

If you change the model, download the model weights before testing offline and ensure the selected runtime supports the model format.

Do not spend the first half of the hackathon compiling and tuning a new inference runtime if a working local model example is already available.

### Model responsibilities

The model should never be responsible for timing the break or deciding whether it was completed.

Those are ordinary application functions.

The local model only handles language-related tasks where it adds value.

This separation makes the system more predictable and easier to debug.

---

## 9. AI Prompt Design

Use a fixed system prompt similar to the following.

> You are Outmark, a practical outdoor activity generator.
>
> Generate one small, safe, realistic screen-free activity based on the user's available time, preferred category, and recent history.
>
> Activities should be possible near home or in a familiar public outdoor space. They should not require equipment, money, internet access, photography, or contact with strangers.
>
> Avoid dangerous routes, trespassing, disturbing wildlife, collecting plants, or activities that require entering private property.
>
> Prefer activities that involve movement, noticing the environment, taking a quiet break, or having meaningful interactions.
>
> Avoid repeating the user's recent activities.
>
> Return valid JSON with these fields only:
>
> `title`, `instructions`, `reflection_question`, `category`.
>
> Keep the title short and the instructions concise. Match the chosen duration. Do not claim that the user has completed the activity.

### Example request

```json
{
  "duration_minutes": 10,
  "preferred_category": "nature_observation",
  "recent_activities": [
    "walked around the neighborhood",
    "watched the sunset"
  ]
}
```

### Example response

```json
{
  "title": "Notice the Small Things",
  "instructions": "Spend ten minutes in a familiar outdoor place. Find three different leaf shapes or patterns without picking anything.",
  "reflection_question": "What detail did you notice that you would normally overlook?",
  "category": "nature_observation"
}
```

### Reliability rules

- Limit the requested response to a short output.
- Parse the generated JSON and validate the category.
- Reject malformed or inappropriate output.
- Have a small predefined catalog of fallback activities.
- Never allow model output to control the hardware directly.
- Never allow the model to mark a session completed without a user response.

If inference fails, Outmark should still be able to run the timer and record a session. The fallback activity catalog keeps the core experience available.

---

## 10. Application Architecture

The application can be organized into three main layers.

### Layer A: Local web application

Provides:

- Home page showing recent activity.
- Duration and category selection.
- Generated quest.
- Active-session status.
- Honest completion reporting.
- Reflection form.
- Thirteen-day history view.

Recommended routes:

| Route | Purpose |
|---|---|
| `GET /` | Display the home page and latest grid |
| `POST /api/quest` | Generate a personalized activity |
| `POST /api/session/start` | Start a session |
| `GET /api/session` | Retrieve the current session state |
| `POST /api/session/report` | Record the user's completion response |
| `GET /api/history` | Return the latest 13 days of history |

### Layer B: Python application

The Python side handles all application logic.

Responsibilities:

- Call the local model server.
- Validate model output.
- Store sessions and reflections.
- Calculate elapsed time.
- Compute the 8 × 13 history grid.
- Send display commands to the microcontroller.
- Restore session state after an application restart.

### Layer C: Arduino sketch

The sketch maintains a compact display state.

For example, define four display modes:

- `GRID`: show the 13-day activity record.
- `ACTIVE`: show the current break progress.
- `DONE`: show a completed-timer symbol.
- `REST`: show an idle symbol when no session is active.

Use `Arduino_LED_Matrix` to draw fixed 104-pixel frames.

Use `Arduino_RouterBridge` to expose simple MCU functions such as `set_mode`, `set_progress`, and `set_grid_row`.

Each history row can be transferred as an integer bit mask: 13 bits represent that category's recorded activity across 13 days.

The MCU stores the latest masks and redraws the matrix whenever the display mode or history changes.

This is more efficient and easier to debug than repeatedly transferring a complete image.

---

## 11. Data Storage Design

Store a single local JSON file initially.

Example:

```json
{
  "settings": {
    "default_duration": 10
  },
  "sessions": [
    {
      "id": "session-001",
      "started_at": "2026-10-10T12:00:00+05:45",
      "duration_minutes": 10,
      "category": "nature_observation",
      "quest": "Find three different leaf patterns.",
      "status": "kept",
      "reflection": "I noticed a different pattern on each leaf.",
      "reported_at": "2026-10-10T12:15:00+05:45"
    }
  ]
}
```

The timestamp is an illustrative example.

### Supported session states

- `active`: timer has started, and no final response has been recorded.
- `kept`: user reports fulfilling the commitment.
- `not_kept`: user reports that they did not fulfill it.

An expired timer does not automatically mean that a commitment was kept.

### Updating the 13-day grid

On every successful report:

1. Save the session locally.
2. Determine the activity category.
3. Find the session date.
4. Set the matching cell in the corresponding history row.
5. Render the updated matrix.
6. Refresh the webpage.

The 13-day view should roll forward automatically, removing dates older than the selected window without deleting the full historical record.

---

## 12. Timer and Display Logic

The Python application should be the authoritative timer because it can save timestamps and recover from restarts.

When the user starts a session:

1. Save the start timestamp and duration.
2. Set the session to `active`.
3. Send the active display state to the STM32.
4. Update the progress indicator at a low frequency, such as every five seconds.
5. Continue counting even if the browser closes.

Calculate progress using elapsed time divided by the duration, clamped between zero and one.

The Arduino sketch should not block while waiting for the timer to finish.

When the deadline passes, switch to `DONE`. The user must still report the result manually.

When the user confirms completion, the application saves the session and returns the display to `GRID`.

If the user reports that they did not complete the activity, retain the session history but do not illuminate a completed-activity cell.

Use neutral visual feedback for missed commitments. Avoid a punishment mechanic.

---

## 13. Five-Hour Implementation Schedule

The following is a strict MVP schedule. It assumes the Arduino UNO Q is already functional and you can access Arduino App Lab.

### Hour 1 — Board setup and local AI

- Open Arduino App Lab.
- Run a basic MCU sketch to verify matrix operation.
- Start a known working local LLM example.
- Verify that Python can send a prompt to the local inference endpoint.
- Generate one sample activity.

**Milestone:** The model generates a short activity locally on the UNO Q.

Do not proceed with model tuning if the basic local inference path is broken.

### Hour 2 — Web interface and data model

- Build a simple Flask application.
- Create the duration and category selector.
- Implement the quest-generation endpoint.
- Save sessions to JSON.
- Create the completion-report form.

**Milestone:** You can create a quest, start a session, and save its result.

### Hour 3 — LED matrix

- Create the Arduino sketch using `Arduino_LED_Matrix`.
- Implement the four display modes.
- Expose display functions through Arduino Bridge.
- Send the eight row masks from Python.
- Render the history grid.

**Milestone:** Completing a session changes the physical matrix.

### Hour 4 — Timer and AI adaptation

- Implement persistent session timing.
- Restore active sessions after app restart.
- Add JSON validation and fallback activities.
- Pass recent activity history into the model prompt.
- Ensure missed sessions never erase recorded progress.

**Milestone:** Outmark works end to end without requiring the user to keep the webpage open.

### Hour 5 — Testing and demonstration

- Generate several quests.
- Test completion and non-completion flows.
- Test the rolling 13-day window.
- Disconnect the external internet and verify that local inference still works.
- Take the device through a real screen-free break demonstration.
- Fix bugs before attempting optional improvements.

**Milestone:** A working local-AI project whose real-world activity changes its physical display.

---

## 14. Required MVP Features

The hackathon version is complete when it can:

1. Generate one personalized outdoor activity using an open-weight model running locally.
2. Start a session and continue its timer without the browser remaining open.
3. Record the user's honest completion report.
4. Store the session locally.
5. Update the 8 × 13 matrix based on reported activity.
6. Adapt a subsequent suggestion using recent history.
7. Work without external internet after the model and dependencies have been installed.

The interface does not need accounts, cloud databases, maps, camera access, or external APIs.

---

## 15. Testing Checklist

### AI and privacy

- The model endpoint points to the local device.
- Activity generation still works with the external internet disconnected.
- Malformed output triggers a safe fallback activity.
- User reflections are stored locally.
- Photographs and location data are not required.

### Timer and reporting

- A session continues if the browser closes.
- A restart restores the correct session state.
- An expired timer never automatically marks an activity completed.
- Reporting failure does not delete earlier records.

### Display

- The matrix starts in an appropriate state.
- Progress advances while a session is active.
- Completion changes the matrix.
- The history grid represents the correct categories and dates.
- The matrix returns to history mode after reporting.

### Usability

- A new user can start a session without reading a manual.
- All challenges can be performed without additional equipment.
- The activity fits the selected time.
- A missed commitment does not punish or shame the user.

---

## 16. Risks and Fallbacks

### Model inference is too slow

Limit generation to one short activity per session. Reuse the local LLM example rather than building a new inference runtime. Fall back to predefined challenges if necessary.

### The web application loses its connection to the browser

The Linux application should continue the timer and preserve session state. The browser can reload the latest state when the user returns.

### Matrix communication is unreliable

Test matrix rendering and Arduino Bridge in isolation before integrating the model. Keep display functions simple and pass compact integer state values.

### The AI repeats itself

Pass the last few activities as context and ask for a different category or task. Retain fallback templates.

### Users can falsely report completion

This cannot be solved honestly with the available hardware. Outmark should explicitly treat history as self-reported activity rather than verified evidence.

---

## 17. What Not to Build

To finish the project in five hours, exclude:

- Automatic location tracking.
- Activity verification using a camera.
- Speech recognition or generation.
- A complex agent framework.
- User accounts and synchronization.
- A full-screen pixel-art game.
- Multiple language models.
- Fine-tuning.
- Elaborate animations.

The physical display, commitment workflow, local AI, and activity record are the product. Everything else is secondary.

## 18. Final Hackathon Pitch

**Outmark: Your offline life, made visible.**

Outmark is a physical self-accountability device powered by open-weight AI. It helps people step away from their screens, make manageable outdoor commitments, and record what they experience.

A local model generates personalized challenges based on the user's recent habits. The UNO Q's LED matrix turns those self-reported commitments into a rolling 13-day visual record.

The system operates locally, keeps reflections on the device, and does not claim to monitor or enforce user behavior.

**Why open innovation matters:** The AI runs on user-controlled hardware, the model can be replaced, the prompts and logic can be modified, and the data stays local. Outmark demonstrates an open-AI interaction that works without a cloud dependency.

**Closing line:**

"We built a device that cannot tell whether you're being honest. It doesn't need to. Outmark makes your commitments visible and leaves the discipline itself in your hands."