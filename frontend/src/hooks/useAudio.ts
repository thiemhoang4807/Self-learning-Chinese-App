import { useCallback, useEffect, useRef, useState } from 'react'
import { audioUrl } from '../lib/api'
import { startPlayback } from '../lib/audio'

export function useAudio() {
  const active = useRef<{ cancel: () => void } | null>(null)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')

  const stop = useCallback(() => {
    const request = active.current
    active.current = null
    request?.cancel()
    setPlaying(false)
  }, [])

  useEffect(() => () => {
    active.current?.cancel()
    active.current = null
  }, [])

  const play = useCallback((text: string, rate = 1, onEnded?: () => void) => {
    stop()
    setError('')
    const request = { cancel: () => {} }
    active.current = request
    request.cancel = startPlayback({
      url: audioUrl(text, rate),
      text,
      rate,
      onPlaying: () => {
        if (active.current === request) setPlaying(true)
      },
      onSettled: message => {
        if (active.current !== request) return
        active.current = null
        setPlaying(false)
        setError(message ?? '')
        onEnded?.()
      },
    })
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
