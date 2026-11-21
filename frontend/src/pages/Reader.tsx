import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { BookOpenText, Plus, X } from 'lucide-react'
import { Hanzi, useExperience, WordDefinition } from '../components/Experience'
import { Button, ErrorNotice, LevelBadge, Loading, Panel, StatusBadge } from '../components/ui'
import { api, errorMessage, queueItems } from '../lib/api'
import type { ReaderToken, Word } from '../types'

interface ReaderSelection {
  index: number
  anchor: HTMLButtonElement
  top: number
  left: number
  below: boolean
}

export function Reader() {
  const { preferences, notify } = useExperience()
  const [text, setText] = useState('')
  const [tokens, setTokens] = useState<ReaderToken[]>([])
  const [reading, setReading] = useState(false)
  const [readError, setReadError] = useState('')
  const [selection, setSelection] = useState<ReaderSelection | null>(null)
  const [lookup, setLookup] = useState<string | null>(null)
  const [lookupError, setLookupError] = useState('')
  const [queueing, setQueueing] = useState(false)
  const popover = useRef<HTMLDivElement>(null)
  const result = useRef<HTMLElement>(null)
  const request = useRef<AbortController | null>(null)
  const segmentation = useRef<AbortController | null>(null)
  const activeToken = selection ? tokens[selection.index] : null

  useEffect(() => () => {
    request.current?.abort()
    segmentation.current?.abort()
  }, [])

  useEffect(() => {
    if (!selection) return
    popover.current?.focus({ preventScroll: true })
    function close() {
      request.current?.abort()
      setSelection(null)
    }
    function pointer(event: PointerEvent) {
      if (event.target instanceof Node && (popover.current?.contains(event.target) || selection?.anchor.contains(event.target))) return
      close()
    }
    function key(event: KeyboardEvent) {
      if (event.key === 'Escape' && !document.querySelector('dialog[open]')) {
        close()
        selection?.anchor.focus()
      }
    }
    function scrolled(event: Event) {
      if (event.target instanceof Node && popover.current?.contains(event.target)) return
      close()
    }
    document.addEventListener('pointerdown', pointer)
    document.addEventListener('keydown', key)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', scrolled, true)
    return () => {
      document.removeEventListener('pointerdown', pointer)
      document.removeEventListener('keydown', key)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', scrolled, true)
    }
  }, [selection])

  async function segment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim() || reading) return
    const controller = new AbortController()
    segmentation.current?.abort()
    request.current?.abort()
    segmentation.current = controller
    setSelection(null)
    setReadError('')
    setReading(true)
    try {
      const response = await api<{ tokens: ReaderToken[] }>('/reader/segment', { body: { text }, signal: controller.signal })
      if (controller.signal.aborted) return
      setTokens(response.tokens)
      requestAnimationFrame(() => result.current?.focus({ preventScroll: true }))
    } catch (cause) {
      if (!controller.signal.aborted) setReadError(errorMessage(cause))
    } finally {
      if (!controller.signal.aborted) setReading(false)
    }
  }

  function updateWord(term: string, word: Word) {
    setTokens(current => current.map(token => token.text === term || token.word?.id === word.id ? { ...token, word } : token))
  }

  async function lookupWord(token: ReaderToken) {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setLookup(token.text)
    setLookupError('')
    try {
      const word = await api<Word>('/reader/lookup', { body: { word: token.text }, signal: controller.signal })
      if (!controller.signal.aborted) updateWord(token.text, word)
    } catch (cause) {
      if (!controller.signal.aborted) setLookupError(errorMessage(cause))
    } finally {
      if (!controller.signal.aborted) setLookup(null)
    }
  }

  function open(index: number, anchor: HTMLButtonElement) {
    if (selection?.index === index) {
      request.current?.abort()
      setSelection(null)
      return
    }
    const rect = anchor.getBoundingClientRect()
    const menuWidth = Math.min(352, window.innerWidth - 24)
    const below = window.innerHeight - rect.bottom > 300 || rect.top < 300
    const left = Math.min(window.innerWidth - menuWidth - 12, Math.max(12, rect.left))
    const top = below ? rect.bottom + 8 : rect.top - 8
    setSelection({ index, anchor, left, top, below })
    setLookup(null)
    setLookupError('')
    request.current?.abort()
    if (!tokens[index].word?.meaning_vi) void lookupWord(tokens[index])
  }

  async function add(word: Word, term: string) {
    setQueueing(true)
    setLookupError('')
    try {
      await queueItems('word', [word.id])
      updateWord(term, { ...word, status: 'new' })
      notify('Đã thêm “' + word.simplified + '” vào kho ôn.')
    } catch (cause) {
      setLookupError(errorMessage(cause))
    } finally {
      setQueueing(false)
    }
  }

  return <div className="page-stack">
    <Panel title="Trình đọc">
      <form className="page-stack" onSubmit={event => void segment(event)}>
        <label>Đoạn tiếng Trung
          <textarea className="reader-input" lang="zh-Hans" rows={5} value={text} maxLength={10000}
            onChange={event => setText(event.target.value)} placeholder="Dán đoạn văn bạn muốn đọc" />
        </label>
        <div className="actions"><Button type="submit" variant="primary" disabled={reading || !text.trim()}><BookOpenText size={18} />
          {reading ? 'Đang tách từ…' : 'Mở đoạn đọc'}</Button></div>
      </form>
      <ErrorNotice message={readError} />
    </Panel>
    {tokens.length > 0 && <section className="panel" ref={result} tabIndex={-1}>
      <div className="split reader-heading"><h2>Đoạn đọc</h2><div className="reader-legend">
        <span className="legend-unknown">Chưa ôn</span><span className="legend-learning">Đang học</span><span className="legend-mastered">Đã thuộc</span>
      </div></div>
      <div className="reader-passage" lang="zh-Hans">
        {tokens.map((token, index) => {
          if (!/\p{Script=Han}/u.test(token.text)) return <span key={index}>{token.text}</span>
          return <button key={index} type="button" className={'reader-token reader-' + (token.word?.status ?? 'unknown')}
            onClick={event => open(index, event.currentTarget)} aria-expanded={selection?.index === index}
            aria-label={'Tra từ ' + token.text}>
            {preferences.pinyin && token.word?.pinyin ? <ruby>{token.text}<rt>{token.word.pinyin}</rt></ruby> : token.text}
          </button>
        })}
      </div>
    </section>}

    {selection && activeToken && <div role="region" aria-label={'Giải nghĩa ' + activeToken.text} ref={popover} tabIndex={-1}
      style={{ top: selection.top, left: selection.left, transform: selection.below ? undefined : 'translateY(-100%)' }} className="reader-popover">
      <Button className="icon-button popover-close" variant="quiet" aria-label="Đóng giải nghĩa" onClick={() => {
        request.current?.abort()
        setSelection(null)
        selection.anchor.focus()
      }}><X size={18} /></Button>
      {activeToken.word ? <>
        <WordDefinition word={activeToken.word} />
        <div className="actions"><LevelBadge level={activeToken.word.hsk_level} />
          {activeToken.word.status && activeToken.word.status !== 'ignored' ? <StatusBadge status={activeToken.word.status} />
            : <Button onClick={() => activeToken.word && void add(activeToken.word, activeToken.text)} disabled={queueing}><Plus size={16} />Thêm vào kho ôn</Button>}
        </div>
      </> : <>
        <Hanzi text={activeToken.text} className="word-heading" />
        {lookup === activeToken.text && <Loading label="Đang tra nghĩa…" />}
      </>}
      <ErrorNotice message={lookupError} retry={activeToken.word ? undefined : () => void lookupWord(activeToken)} />
    </div>}
  </div>
}
