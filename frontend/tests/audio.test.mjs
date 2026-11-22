import assert from 'node:assert/strict'
import { test } from 'node:test'
import { moduleUrl } from './load-module.mjs'

const { startPlayback } = await import(await moduleUrl('lib/audio.ts'))

function fixture({ voices = ['en-US', 'zh-HK', 'zh-CN'], webSpeech = true } = {}) {
  const events = []
  const media = {
    duration: 3.5,
    play: async () => {},
    pause: () => {},
    removeAttribute: () => {},
    load: () => {},
  }
  const voiceEvents = new EventTarget()
  const speech = {
    getVoices: () => voices.map(lang => ({ lang })),
    addEventListener: voiceEvents.addEventListener.bind(voiceEvents),
    removeEventListener: voiceEvents.removeEventListener.bind(voiceEvents),
    speak: utterance => { speech.lastLine = utterance },
    cancel: () => { speech.canceled += 1 },
    canceled: 0,
  }
  let id = 0
  const timers = new Map()
  const environment = {
    audio: url => {
      assert.equal(url, '/api/audio/tts?text=Chinese')
      return media
    },
    synthesis: webSpeech ? speech : undefined,
    utterance: text => ({ text }),
    schedule: (callback, delay) => {
      timers.set(++id, { callback, delay })
      return id
    },
    unschedule: timer => timers.delete(timer),
  }
  const start = (text = '你好') => startPlayback({
    url: '/api/audio/tts?text=Chinese',
    text,
    rate: 1.2,
    onPlaying: () => events.push('playing'),
    onSettled: error => events.push(error ?? 'ended'),
  }, environment)
  const advance = () => {
    const next = timers.entries().next()
    assert.equal(next.done, false)
    const [timer, { callback, delay }] = next.value
    timers.delete(timer)
    callback()
    return delay
  }
  return { start, advance, media, speech, voiceEvents, timers, events }
}

test('plays cached or generated MP3 to completion without speech synthesis', () => {
  const { start, media, events, speech, timers } = fixture()
  start()
  media.onplaying()
  media.onended()
  assert.deepEqual(events, ['playing', 'ended'])
  assert.equal(speech.lastLine, undefined)
  assert.equal(timers.size, 0)
})

test('falls back after a media fetch failure using zh-CN and the requested rate', () => {
  const { start, media, speech, events } = fixture()
  start()
  media.onerror()
  const utterance = speech.lastLine
  assert.equal(utterance.text, '你好')
  assert.equal(utterance.lang, 'zh-CN')
  assert.equal(utterance.voice.lang, 'zh-CN')
  assert.equal(utterance.rate, 1.2)
  utterance.onstart()
  utterance.onend()
  assert.deepEqual(events, ['playing', 'ended'])
})

test('uses a Chinese voice after asynchronous voice initialization', () => {
  const voices = []
  const { start, media, speech, voiceEvents, events } = fixture({ voices })
  start()
  media.onerror()
  assert.equal(speech.lastLine, undefined)
  voices.push('zh-CN')
  voiceEvents.dispatchEvent(new Event('voiceschanged'))
  speech.lastLine.onend()
  assert.deepEqual(events, ['ended'])
})

test('settles if the provider stalls and the device has no Chinese voice', () => {
  const { start, advance, events, timers } = fixture({ voices: ['en-US', 'zh-HK'] })
  start()
  assert.equal(advance(), 13000)
  assert.equal(advance(), 1300)
  assert.deepEqual(events, ['Không có giọng tiếng Trung khả dụng trên thiết bị này.'])
  assert.equal(timers.size, 0)
})

test('settles after a synth error or on browsers without speech synthesis', () => {
  const synthesis = fixture()
  synthesis.start()
  synthesis.media.onerror()
  synthesis.speech.lastLine.onerror({ error: 'synthesis-unavailable' })
  assert.match(synthesis.events[0], /Chưa phát được âm thanh/)
  assert.equal(synthesis.timers.size, 0)
  const browser = fixture({ webSpeech: false })
  browser.start()
  browser.media.onerror()
  assert.match(browser.events[0], /Không có giọng tiếng Trung/)
  assert.equal(browser.timers.size, 0)
})

test('uses a safety timer if speech synthesis does not dispatch its end event', () => {
  const { start, media, speech, advance, events, timers } = fixture()
  start()
  media.onerror()
  speech.lastLine.onstart()
  assert.equal(advance(), 7000)
  assert.equal(speech.canceled, 1)
  assert.match(events[1], /Chưa phát được âm thanh/)
  assert.equal(timers.size, 0)
})

test('cancellation drops stale callbacks and does not advance the playlist', () => {
  const { start, media, speech, events, timers } = fixture()
  const cancel = start()
  media.onerror()
  const staleEnded = speech.lastLine.onend
  cancel()
  staleEnded()
  assert.deepEqual(events, [])
  assert.equal(timers.size, 0)
  assert.equal(speech.canceled, 1)
})
