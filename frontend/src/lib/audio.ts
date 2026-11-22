type Timer = ReturnType<typeof setTimeout>

interface PlaybackEnvironment {
  audio: (url: string) => HTMLAudioElement
  synthesis?: SpeechSynthesis
  utterance?: (text: string) => SpeechSynthesisUtterance
  schedule: (task: () => void, delay: number) => Timer
  unschedule: (timer: Timer) => void
}

interface PlaybackRequest {
  url: string
  text: string
  rate: number
  onPlaying: () => void
  onSettled: (error?: string) => void
}

const unavailable = 'Không có giọng tiếng Trung khả dụng trên thiết bị này.'
const playbackFailed = 'Chưa phát được âm thanh. Bạn có thể tiếp tục học hoặc thử lại.'
const autoplayBlocked = 'Bấm nút nghe để cho phép trình duyệt phát âm thanh.'
let speechOwner: SpeechSynthesisUtterance | undefined

function browserEnvironment(): PlaybackEnvironment {
  return {
    audio: url => new Audio(url),
    synthesis: window.speechSynthesis,
    utterance: typeof SpeechSynthesisUtterance === 'function' ? text => new SpeechSynthesisUtterance(text) : undefined,
    schedule: (task, delay) => setTimeout(task, delay),
    unschedule: timer => clearTimeout(timer),
  }
}

function chineseVoice(synthesis: SpeechSynthesis) {
  const voices = synthesis.getVoices()
  return voices.find(voice => /^zh[-_]CN$/i.test(voice.lang))
    ?? voices.find(voice => /^(?:(?:zh|cmn)[-_](?:Hans(?:[-_]CN)?|CN|SG)|zh)$/i.test(voice.lang))
}

export function startPlayback(
  { url, text, rate, onPlaying, onSettled }: PlaybackRequest,
  environment = browserEnvironment(),
) {
  const { audio, synthesis, schedule, unschedule, utterance } = environment
  let media: HTMLAudioElement | undefined
  let voiceLine: SpeechSynthesisUtterance | undefined
  let stopWaitingForVoices: (() => void) | undefined
  let timer: Timer | undefined
  let closed = false
  let fallbackStarted = false

  function clearTimer() {
    if (timer !== undefined) unschedule(timer)
    timer = undefined
  }

  function arm(task: () => void, timeout: number) {
    clearTimer()
    timer = schedule(task, timeout)
  }

  function stopMedia() {
    if (!media) return
    media.onplaying = null
    media.onended = null
    media.onerror = null
    media.pause()
    media.removeAttribute('src')
    media.load()
    media = undefined
  }

  function cleanup() {
    closed = true
    clearTimer()
    stopMedia()
    stopWaitingForVoices?.()
    if (voiceLine) {
      voiceLine.onstart = null
      voiceLine.onend = null
      voiceLine.onerror = null
      if (speechOwner === voiceLine) {
        speechOwner = undefined
        synthesis?.cancel()
      }
    }
  }

  function finish(error?: string) {
    if (closed) return
    cleanup()
    onSettled(error)
  }

  function fallBack(blocked = false) {
    if (closed || fallbackStarted) return
    fallbackStarted = true
    clearTimer()
    stopMedia()
    if (!synthesis || !utterance) {
      finish(blocked ? autoplayBlocked : unavailable)
      return
    }
    const speaker = synthesis
    const createUtterance = utterance
    function speak(voice: SpeechSynthesisVoice) {
      stopWaitingForVoices?.()
      try {
        voiceLine = createUtterance(text)
        voiceLine.lang = 'zh-CN'
        voiceLine.voice = voice
        voiceLine.rate = rate
        voiceLine.onstart = onPlaying
        voiceLine.onend = () => {
          if (speechOwner === voiceLine) speechOwner = undefined
          finish()
        }
        voiceLine.onerror = event => finish(event.error === 'not-allowed' ? autoplayBlocked : playbackFailed)
        speechOwner = voiceLine
        arm(() => finish(playbackFailed), Math.max(7000, Array.from(text).length * 420 / rate + 4000))
        speaker.speak(voiceLine)
      } catch {
        finish(playbackFailed)
      }
    }
    function tryVoice() {
      if (closed || voiceLine) return
      try {
        const voice = chineseVoice(speaker)
        if (voice) speak(voice)
      } catch {
        finish(playbackFailed)
      }
    }
    speaker.addEventListener('voiceschanged', tryVoice)
    stopWaitingForVoices = () => speaker.removeEventListener('voiceschanged', tryVoice)
    arm(() => finish(blocked ? autoplayBlocked : unavailable), 1300)
    tryVoice()
  }

  if (!text.trim()) {
    finish()
    return cleanup
  }

  try {
    media = audio(url)
    media.onplaying = () => {
      if (!media || closed) return
      const duration = Number.isFinite(media.duration) ? media.duration * 1000 + 3500 : 0
      arm(() => fallBack(), Math.max(duration, Array.from(text).length * 430 / rate + 5000))
      onPlaying()
    }
    media.onended = () => finish()
    media.onerror = () => fallBack()
    arm(() => fallBack(), 13_000)
    void media.play().catch(error => fallBack(error instanceof DOMException && error.name === 'NotAllowedError'))
  } catch {
    fallBack()
  }

  return cleanup
}
