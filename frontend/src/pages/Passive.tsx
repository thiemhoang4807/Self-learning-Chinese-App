import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AudioLines, Check, Headphones, Pause, Play, Repeat2, SkipBack, SkipForward } from 'lucide-react'
import { Hanzi, Pinyin } from '../components/Experience'
import { Button, Empty, ErrorNotice, Loading, PageTitle, Panel } from '../components/ui'
import { useAudio, usePreloadAudio } from '../hooks/useAudio'
import { useResource } from '../hooks/useResource'
import { api, errorMessage, reviewToken, withQuery } from '../lib/api'
import type { Card } from '../types'

type Phase = 'audio' | 'recall' | 'revealed'

export function Passive() {
  const [params] = useSearchParams()
  const resource = useResource<{ cards: Card[] }>(withQuery('/study/session', {
    size: params.get('size') ?? 10,
    mode: 'flashcard',
    source_id: params.get('source_id'),
    hsk_level: params.get('hsk_level'),
  }))

  return <div className="page-stack">
    <PageTitle title="Chế độ Học Lười" description="Nghe tiếng Trung, nhẩm nghĩa vài giây rồi xem thẻ." />
    {resource.loading && <Loading label="Đang chuẩn bị danh sách phát…" />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data && (resource.data.cards.length > 0 ? <Player cards={resource.data.cards} />
      : <Panel><Empty>Chưa có thẻ phù hợp để nghe.</Empty><Link className="button button-secondary" to="/">Về Học hôm nay</Link></Panel>)}
  </div>
}

function Player({ cards }: { cards: Card[] }) {
  const [index, setIndex] = useState(0)
  const [phase, setPhase] = useState<Phase>('audio')
  const [playing, setPlaying] = useState(false)
  const [rate, setRate] = useState(1)
  const [delay, setDelay] = useState(3)
  const [loop, setLoop] = useState(false)
  const [finished, setFinished] = useState(false)
  const [marking, setMarking] = useState(false)
  const [marked, setMarked] = useState<number[]>([])
  const [tokens, setTokens] = useState<Record<number, string>>({})
  const [error, setError] = useState('')
  const card = cards[index]
  const audio = useAudio()
  const { play, stop } = audio
  const audioError = audio.error
  const currentAudio = card.audio_text || card.hanzi
  usePreloadAudio(cards.slice(index + 1, index + 4).map(value => value.audio_text || value.hanzi), rate)

  useEffect(() => {
    if (audioError) setPlaying(false)
  }, [audioError])

  useEffect(() => {
    if (!playing) return
    if (phase === 'audio') {
      play(currentAudio, rate, () => setPhase('recall'))
      return stop
    }
    const timer = window.setTimeout(() => {
      if (phase === 'recall') {
        setPhase('revealed')
        return
      }
      if (index + 1 < cards.length || loop) {
        setIndex((index + 1) % cards.length)
        setPhase('audio')
      } else {
        setPlaying(false)
        setFinished(true)
      }
    }, phase === 'recall' ? delay * 1000 : 2900)
    return () => window.clearTimeout(timer)
  }, [playing, phase, currentAudio, rate, index, cards.length, loop, delay, play, stop])

  function move(step: number) {
    const next = index + step
    if (!loop && (next < 0 || next >= cards.length)) return
    setFinished(false)
    setIndex((next + cards.length) % cards.length)
    setPhase('audio')
  }

  function togglePlay() {
    if (finished) {
      setFinished(false)
      setIndex(0)
      setPhase('audio')
    }
    setPlaying(value => !value)
  }

  async function mark() {
    if (marking || marked.includes(card.id)) return
    setMarking(true)
    setError('')
    const token = tokens[card.id] || reviewToken()
    setTokens(current => ({ ...current, [card.id]: token }))
    try {
      await api('/study/cards/' + card.id + '/review', { body: {
        rating: 1, drill_mode: 'passive', response_ms: 0, review_token: token,
      } })
      setMarked(current => [...current, card.id])
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setMarking(false)
    }
  }

  const playerLabel = playing ? 'Tạm dừng' : finished ? 'Nghe lại' : 'Phát'
  return <>
    <Panel className="player">
      <div className="split"><strong><Headphones size={20} className="inline-icon" /> Danh sách nghe</strong><span>{index + 1} / {cards.length}</span></div>
      <div className="player-face" aria-live="polite">
        {phase === 'revealed' ? <>
          <Hanzi text={card.hanzi} className="focus-hanzi" />
          <Pinyin text={card.pinyin} />
          {card.han_viet && <span className="han-viet">{card.han_viet}</span>}
          <p>{card.meaning_vi}</p>
        </> : <>
          <span className={'listen-orb' + (playing && phase === 'audio' ? ' is-playing' : '')}><AudioLines size={38} /></span>
          <h2>{phase === 'recall' ? 'Bạn nhớ nghĩa của từ này không?' : playing ? 'Nghe tiếng Trung' : 'Sẵn sàng nghe'}</h2>
        </>}
      </div>
      <div className="player-controls">
        <Button className="icon-button" variant="quiet" aria-label="Thẻ trước" title="Thẻ trước" disabled={!loop && index === 0} onClick={() => move(-1)}><SkipBack size={23} /></Button>
        <Button className="play-button" variant="primary" onClick={togglePlay} aria-label={playerLabel}>{playing ? <Pause size={25} /> : <Play size={25} />}{playerLabel}</Button>
        <Button className="icon-button" variant="quiet" aria-label="Thẻ tiếp" title="Thẻ tiếp" disabled={!loop && index + 1 === cards.length} onClick={() => move(1)}><SkipForward size={23} /></Button>
      </div>
      <div className="player-settings">
        <label>Tốc độ
          <select value={rate} onChange={event => setRate(Number(event.target.value))}>
            <option value={0.85}>0,85 ×</option><option value={1}>1,0 ×</option><option value={1.2}>1,2 ×</option>
          </select>
        </label>
        <label>Chờ nhẩm nghĩa
          <select value={delay} onChange={event => setDelay(Number(event.target.value))}>
            <option value={2}>2 giây</option><option value={3}>3 giây</option>
          </select>
        </label>
        <Button aria-pressed={loop} onClick={() => setLoop(value => !value)}><Repeat2 size={18} />Lặp danh sách</Button>
      </div>
      <ErrorNotice message={audio.error || error} />
      <Button variant="quiet" disabled={marking || marked.includes(card.id)} onClick={() => void mark()}>
        {marked.includes(card.id) ? <><Check size={18} />Đã đánh dấu chưa nhớ</> : 'Đánh dấu chưa nhớ'}
      </Button>
    </Panel>
    <Link to="/" className="text-link">Về Học hôm nay</Link>
  </>
}
