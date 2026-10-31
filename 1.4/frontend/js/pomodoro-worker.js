/**
 * Dream Hub v1.4.0 - Resilient Background Pomodoro & Daily Routine Web Worker (RNF03)
 * Uses real wall-clock timestamps (Date.now()) to prevent drift or WebView throttling.
 */

let timerInterval = null;
let endTimeMs = null;
let remainingSeconds = 0;
let isRunning = false;
let routineStartWallMs = null;
let routineBaseElapsedSec = 0;
let lastKnownDateStr = new Date().toISOString().slice(0, 10);

function computeCurrentState() {
  const now = Date.now();
  const todayStr = new Date(now).toISOString().slice(0, 10);
  const dateTurnedOver = (todayStr !== lastKnownDateStr);
  if (dateTurnedOver) {
    lastKnownDateStr = todayStr;
  }

  let currentRemSec = remainingSeconds;
  let completed = false;
  if (isRunning && endTimeMs) {
    currentRemSec = Math.max(0, Math.ceil((endTimeMs - now) / 1000));
    remainingSeconds = currentRemSec;
    if (currentRemSec <= 0) {
      isRunning = false;
      endTimeMs = null;
      completed = true;
    }
  }

  let routineElapsedSec = routineBaseElapsedSec;
  if (routineStartWallMs) {
    routineElapsedSec = routineBaseElapsedSec + Math.max(0, Math.floor((now - routineStartWallMs) / 1000));
  }

  return {
    type: completed ? 'COMPLETE' : 'TICK',
    remainingSeconds: currentRemSec,
    isRunning,
    routineElapsedSeconds: routineElapsedSec,
    dateTurnedOver,
    todayStr,
    timestamp: now
  };
}

function startLoop() {
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    const state = computeCurrentState();
    self.postMessage(state);
    if (state.type === 'COMPLETE') {
      stopLoopIfIdle();
    }
  }, 250);
}

function stopLoopIfIdle() {
  if (!isRunning && !routineStartWallMs) {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }
}

self.onmessage = function(e) {
  const msg = e.data || {};
  const cmd = msg.command;

  if (cmd === 'START') {
    remainingSeconds = Math.max(1, parseInt(msg.remainingSeconds || 1500, 10));
    endTimeMs = msg.endTime || (Date.now() + remainingSeconds * 1000);
    isRunning = true;
    startLoop();
    self.postMessage(computeCurrentState());
  } else if (cmd === 'PAUSE') {
    if (isRunning && endTimeMs) {
      remainingSeconds = Math.max(0, Math.ceil((endTimeMs - Date.now()) / 1000));
    } else if (typeof msg.remainingSeconds === 'number') {
      remainingSeconds = msg.remainingSeconds;
    }
    isRunning = false;
    endTimeMs = null;
    if (routineStartWallMs) {
      routineBaseElapsedSec += Math.max(0, Math.floor((Date.now() - routineStartWallMs) / 1000));
      routineStartWallMs = null;
    }
    self.postMessage({
      type: 'PAUSED',
      remainingSeconds,
      isRunning: false,
      routineElapsedSeconds: routineBaseElapsedSec,
      timestamp: Date.now()
    });
    stopLoopIfIdle();
  } else if (cmd === 'RESET') {
    isRunning = false;
    endTimeMs = null;
    remainingSeconds = Math.max(0, parseInt(msg.remainingSeconds || 1500, 10));
    self.postMessage({
      type: 'RESET',
      remainingSeconds,
      isRunning: false,
      routineElapsedSeconds: routineBaseElapsedSec,
      timestamp: Date.now()
    });
    stopLoopIfIdle();
  } else if (cmd === 'ADJUST') {
    const deltaSec = parseInt(msg.deltaSeconds || 0, 10);
    if (isRunning && endTimeMs) {
      endTimeMs = Math.max(Date.now() + 1000, endTimeMs + deltaSec * 1000);
      remainingSeconds = Math.max(1, Math.ceil((endTimeMs - Date.now()) / 1000));
    } else {
      remainingSeconds = Math.max(60, remainingSeconds + deltaSec);
    }
    self.postMessage(computeCurrentState());
  } else if (cmd === 'ROUTINE_START') {
    routineBaseElapsedSec = Math.max(0, parseInt(msg.elapsedSeconds || 0, 10));
    routineStartWallMs = Date.now();
    startLoop();
    self.postMessage(computeCurrentState());
  } else if (cmd === 'ROUTINE_PAUSE') {
    if (routineStartWallMs) {
      routineBaseElapsedSec += Math.max(0, Math.floor((Date.now() - routineStartWallMs) / 1000));
      routineStartWallMs = null;
    }
    if (isRunning && endTimeMs) {
      remainingSeconds = Math.max(0, Math.ceil((endTimeMs - Date.now()) / 1000));
      isRunning = false;
      endTimeMs = null;
    }
    self.postMessage({
      type: 'PAUSED',
      remainingSeconds,
      isRunning: false,
      routineElapsedSeconds: routineBaseElapsedSec,
      timestamp: Date.now()
    });
    stopLoopIfIdle();
  } else if (cmd === 'SYNC') {
    self.postMessage(computeCurrentState());
  }
};
