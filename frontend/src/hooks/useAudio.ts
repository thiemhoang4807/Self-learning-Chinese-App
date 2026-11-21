import { useCallback, useEffect, useRef, useState } from 'react'
import { audioUrl } from '../lib/api'

export function useAudio() {
  const active = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')

  const stop = useCallback(() => {
    const audio = active.current
    active.current = null
    audio?.pause()
    setPlaying(false)
  }, [])

  useEffect(() => () => active.current?.pause(), [])

  const play = useCallback((text: string, rate = 1, onEnded?: () => void) => {
    stop()
    setError('')
    if (!text.trim()) return
    const audio = new Audio(audioUrl(text, rate))
    active.current = audio
    const fail = (message: string) => {
      if (active.current !== audio) return
      stop()
      setError(message)
    }
    audio.onplaying = () => {
      if (active.current === audio) setPlaying(true)
    }
    audio.onended = () => {
      if (active.current !== audio) return
      stop()
      onEnded?.()
    }
    audio.onerror = () => fail('Chưa phát được âm thanh. Bạn có thể tiếp tục học hoặc thử lại.')
    void audio.play().catch(cause => fail(
      cause instanceof DOMException && cause.name === 'NotAllowedError'
        ? 'Bấm nút nghe để phát âm thanh.'
        : 'Chưa phát được âm thanh. Bạn có thể tiếp tục học hoặc thử lại.',
    ))
  }, [stop])

  return { play, stop, error, playing }
}

export function usePreloadAudio(texts: string[], rate = 1) {
  const preloaded = useRef(new Map<string, HTMLAudioElement>())
  const keys = JSON.stringify(texts.filter(Boolean))
  useEffect(() => {
    const nextTexts: string[] = JSON.parse(keys)
    const nextUrls = new Set(nextTexts.map(text => audioUrl(text, rate)))
    preloaded.current.forEach((audio, url) => {
      if (!nextUrls.has(url)) {
        audio.removeAttribute('src')
        audio.load()
        preloaded.current.delete(url)
      }
    })
    nextUrls.forEach(url => {
      if (!preloaded.current.has(url)) {
        const audio = new Audio()
        audio.preload = 'auto'
        audio.src = url
        preloaded.current.set(url, audio)
      }
    })
  }, [keys, rate])

  useEffect(() => {
    const audioByUrl = preloaded.current
    return () => {
      audioByUrl.forEach(audio => {
        audio.removeAttribute('src')
        audio.load()
      })
      audioByUrl.clear()
    }
  }, [])
}
