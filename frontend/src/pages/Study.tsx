import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { AudioLines, Check, Eye, Lightbulb, Sparkles, Volume2, X } from 'lucide-react'
import { CharacterDetails, Hanzi, Pinyin, useExperience } from '../components/Experience'
import { EditKnowledgeButton } from '../components/KnowledgeEditor'
import { PairClozeQuestions } from '../components/PairClozeQuestions'
import { Button, Empty, ErrorNotice, Loading, Notice, PageTitle, Panel, Speaker } from '../components/ui'
import { useAudio, usePreloadAudio } from '../hooks/useAudio'
import { useResource } from '../hooks/useResource'
import { api, errorMessage, reviewToken, withQuery } from '../lib/api'
import type { Card, DrillMode, Pattern, Rating, ReverseFeedback, Sentence, Word } from '../types'

const labels: Record<DrillMode, string> = {
  flashcard: 'Nhận diện mặt chữ',
  listening: 'Nghe chay',
  cloze: 'Điền từ vào chỗ trống',
  reorder: 'Xếp từ thành câu',
  reverse: 'Dịch Việt sang Trung',
  confusable: 'Phân biệt từ dễ nhầm',
}

const ratingOptions: Array<{ value: Rating; label: string }> = [
  { value: 1, label: 'Chưa nhớ' },
  { value: 2, label: 'Khó nhớ' },
  { value: 3, label: 'Nhớ được' },
  { value: 4, label: 'Dễ nhớ' },
]

const normalizeHanzi = (value: string) => value.normalize('NFKC').replace(/[\p{P}\p{Z}\s]/gu, '')

interface ReviewInput {
  cardId: number
  rating: Rating
  drill_mode: DrillMode
  response_ms: number
  review_token: string
}

export function Study() {
  const [query] = useSearchParams()
  const path = withQuery('/study/session', {
    size: query.get('size') ?? 8,
    mode: query.get('mode') ?? 'mixed',
    source_id: query.get('source_id'),
    hsk_level: query.get('hsk_level'),
    leeches: query.get('leeches'),
  })
  const resource = useResource<{ cards: Card[] }>(path)
  return <div className="page-stack">
    <PageTitle title="Buổi ôn" />
    {resource.loading && <Loading label="Đang chọn thẻ ôn…" />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data && (resource.data.cards.length > 0
      ? <StudySession key={path} cards={resource.data.cards} onRestart={resource.reload} />
      : <Panel><Empty>Chưa có thẻ phù hợp với lựa chọn này.</Empty><Link className="button button-secondary" to="/">Chọn buổi ôn khác</Link></Panel>)}
  </div>
}

function StudySession({ cards: initialCards, onRestart }: { cards: Card[]; onRestart: () => void }) {
  const [cards, setCards] = useState(initialCards)
  const [index, setIndex] = useState(0)
  const [saving, setSaving] = useState(false)
  const [unsaved, setUnsaved] = useState<ReviewInput | null>(null)
  const [reviewError, setReviewError] = useState('')
  const reviewInProgress = useRef(false)
  const card = cards[index]
  usePreloadAudio(cards.slice(index + 1, index + 4).map(item => item.audio_text))

  async function sendReview(input: ReviewInput) {
    if (reviewInProgress.current) return
    reviewInProgress.current = true
    setReviewError('')
    setSaving(true)
    try {
      const { cardId, ...body } = input
      await api('/study/cards/' + cardId + '/review', { body })
      setUnsaved(null)
    } catch (cause) {
      setUnsaved(input)
      setReviewError(errorMessage(cause))
    } finally {
      reviewInProgress.current = false
      setSaving(false)
    }
  }

  function rate(value: Rating, responseTime: number) {
    if (!card || unsaved || reviewInProgress.current) return
    const input = {
      cardId: card.id,
      rating: value,
      drill_mode: card.mode,
      response_ms: Math.min(3_600_000, Math.max(0, Math.round(responseTime))),
      review_token: reviewToken(),
    }
    setIndex(current => current + 1)
    void sendReview(input)
  }

  function saveWord(word: Word) {
    setCards(current => current.flatMap((item, position) => {
      if (item.item_type !== 'word' || item.item_id !== word.id) return [item]
      if (word.status === 'ignored' && position >= index) return []
      return [{
        ...item,
        pinyin: item.hanzi === word.simplified ? word.pinyin : item.pinyin,
        han_viet: word.han_viet,
        meaning_vi: word.meaning_vi,
        mnemonic_vi: word.mnemonic_vi,
        usage_note_vi: word.usage_note_vi,
        status: word.status ?? item.status,
      }]
    }))
  }

  function savePattern(pattern: Pattern) {
    setCards(current => current.map(item => item.item_type === 'pattern' && item.item_id === pattern.id
      ? {
          ...item,
          meaning_vi: item.sentence_id === null ? pattern.explanation_vi : item.meaning_vi,
          usage_note_vi: item.sentence_id === null ? pattern.structure_notes_vi : pattern.explanation_vi,
        }
      : item))
  }

  function saveSentence(sentence: Sentence) {
    setCards(current => current.map(item => {
      const updated = { ...item, sentences: item.sentences.map(previous => previous.id === sentence.id ? sentence : previous) }
      if (item.sentence_id !== sentence.id) return updated
      return {
        ...updated,
        pinyin: sentence.pinyin,
        meaning_vi: item.item_type === 'pattern' ? sentence.meaning_vi : item.meaning_vi,
        prompt: item.mode === 'reverse' || item.mode === 'reorder' ? sentence.meaning_vi : item.prompt,
      }
    }))
  }

  return <>
    {unsaved && <ErrorNotice message={'Chưa lưu được lần ôn vừa rồi. ' + reviewError} retry={() => void sendReview(unsaved)} />}
    <div className="study-progress">
      <div className="split"><span>{card ? labels[card.mode] : 'Hoàn thành'}</span><span>{Math.min(index + 1, cards.length)} / {cards.length}</span></div>
      <progress aria-label="Tiến độ buổi ôn" max={Math.max(cards.length, 1)} value={index} />
    </div>
    {card ? <ReviewCard key={card.id} card={card} onRate={rate} ratingDisabled={saving || Boolean(unsaved)}
      onWordSaved={saveWord} onPatternSaved={savePattern} onSentenceSaved={saveSentence} />
      : <Panel className="session-done">
        <span className="feature-icon"><Check size={24} /></span>
        <h2>{cards.length ? 'Bạn đã ôn ' + cards.length + ' thẻ' : 'Không còn thẻ trong buổi ôn'}</h2>
        {saving && <Loading label="Đang lưu kết quả…" />}
        <div className="actions">
          <Link className="button button-primary" to="/">Về Học hôm nay</Link>
          <Button disabled={saving || Boolean(unsaved)} onClick={onRestart}>Ôn thêm một lượt</Button>
        </div>
      </Panel>}
  </>
}

function ReviewCard({ card, onRate, ratingDisabled, onWordSaved, onPatternSaved, onSentenceSaved }: {
  card: Card
  onRate: (rating: Rating, responseTime: number) => void
  ratingDisabled: boolean
  onWordSaved: (word: Word) => void
  onPatternSaved: (pattern: Pattern) => void
  onSentenceSaved: (sentence: Sentence) => void
}) {
  const { preferences } = useExperience()
  const audio = useAudio()
  const [revealed, setRevealed] = useState(false)
  const [pinyin, setPinyin] = useState<boolean | null>(null)
  const [input, setInput] = useState('')
  const [tiles, setTiles] = useState<number[]>([])
  const [correct, setCorrect] = useState<boolean | null>(null)
  const [rate, setRate] = useState(1)
  const [feedback, setFeedback] = useState<ReverseFeedback | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const started = useRef(performance.now())
  const mode = card.mode
  const play = audio.play
  const listening = mode === 'listening'
  const showPinyinControl = revealed || mode === 'flashcard'
  const canPlay = Boolean(card.audio_text) && (listening || revealed || mode === 'flashcard')
  const pinyinVisible = pinyin ?? (revealed || preferences.pinyin)

  useEffect(() => {
    if (listening) play(card.audio_text, rate)
  }, [listening, play, card.audio_text, rate])

  function togglePinyin() {
    setPinyin(!pinyinVisible)
  }

  function flip() {
    if (busy) return
    if (mode === 'flashcard') setRevealed(value => !value)
    else setRevealed(true)
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.isComposing || document.querySelector('dialog[open]')) return
      const active = event.target instanceof HTMLElement ? event.target : null
      if (active?.closest('input, textarea, select, [contenteditable]')) return
      const key = event.key.toLowerCase()
      if (key === ' ' && !active?.closest('button, a')) {
        event.preventDefault()
        flip()
      } else if (key === 'r' && canPlay) {
        event.preventDefault()
        play(card.audio_text, rate)
      } else if (key === 'p' && showPinyinControl) {
        event.preventDefault()
        togglePinyin()
      } else if (revealed && !ratingDisabled && /^[1-4]$/.test(key)) {
        event.preventDefault()
        onRate(Number(key) as Rating, performance.now() - started.current)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  async function submit(value: string) {
    if (!value.trim() || busy || revealed) return
    setError('')
    if (mode === 'reverse') {
      if (card.sentence_id === null) {
        setError('Thẻ này chưa có câu mẫu để chấm.')
        return
      }
      setBusy(true)
      try {
        setFeedback(await api<ReverseFeedback>('/ai/reverse-translation', { body: { sentence_id: card.sentence_id, answer: value } }))
        setRevealed(true)
      } catch (cause) {
        setError(errorMessage(cause))
      } finally {
        setBusy(false)
      }
      return
    }
    setCorrect(normalizeHanzi(value) === normalizeHanzi(card.answer || card.hanzi))
    setRevealed(true)
  }

  function submitTyped(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submit(input)
  }

  return <>
    <Panel className="review-panel">
      <div className="review-toolbar">
        {showPinyinControl && <Button variant="quiet" aria-pressed={pinyinVisible} onClick={togglePinyin}>
          <Eye size={17} />{pinyinVisible ? 'Ẩn Pinyin' : 'Hiện Pinyin'}
        </Button>}
        {canPlay && <Button variant="quiet" onClick={() => play(card.audio_text, rate)}><Volume2 size={18} />Nghe</Button>}
        {listening && <Button variant="quiet" aria-label="Đổi tốc độ nghe" onClick={() => setRate(rate === 1 ? 1.2 : 1)}>{rate === 1 ? '1,0' : '1,2'} ×</Button>}
      </div>

      {!revealed && mode === 'flashcard' && <div className="flashcard-face">
        <Hanzi className="focus-hanzi" text={card.hanzi} />
        <Pinyin text={card.pinyin} visible={pinyinVisible} />
        <Button variant="primary" onClick={flip}><Eye size={18} />Lật thẻ</Button>
      </div>}

      {!revealed && listening && <div className="listen-face">
        <button type="button" className={'listen-orb' + (audio.playing ? ' is-playing' : '')} onClick={() => play(card.audio_text, rate)} aria-label="Nghe câu" title="Nghe câu">
          <AudioLines size={38} />
        </button>
        <h2>Nghe rồi thử gõ lại</h2>
        <form className="answer-form" onSubmit={submitTyped}>
          <label className="sr-only" htmlFor="listening-answer">Câu bạn nghe được</label>
          <input id="listening-answer" lang="zh-Hans" value={input} onChange={event => setInput(event.target.value)} placeholder="Gõ tiếng Trung" />
          <Button type="submit" variant="primary" disabled={!input.trim()}>Kiểm tra</Button>
        </form>
      </div>}

      {!revealed && mode === 'cloze' && <div className="exercise">
        <h2 className="exercise-prompt"><Hanzi text={card.prompt} /></h2>
        <div className="choices">
          {card.choices.map((choice, optionIndex) => <Button key={optionIndex} onClick={() => void submit(choice)}><Hanzi text={choice} linked={false} /></Button>)}
        </div>
        <form className="answer-form" onSubmit={submitTyped}>
          <label className="sr-only" htmlFor="cloze-answer">Từ còn thiếu</label>
          <input id="cloze-answer" lang="zh-Hans" value={input} onChange={event => setInput(event.target.value)} placeholder="Hoặc gõ từ còn thiếu" />
          <Button type="submit" variant="primary" disabled={!input.trim()}>Kiểm tra</Button>
        </form>
      </div>}

      {!revealed && mode === 'confusable' && <div className="exercise">
        <h2>Chọn từ phù hợp cho từng câu</h2>
        <PairClozeQuestions prompts={pairLines(card.prompt)} choices={card.choices} correct={pairLines(card.answer)}
          onSubmit={answers => void submit(answers.join('\n'))} />
      </div>}

      {!revealed && mode === 'reorder' && <div className="exercise">
        <h2>Xếp các từ theo đúng thứ tự</h2>
        {card.prompt && <p>{card.prompt}</p>}
        <div className="tile-tray" aria-label="Câu của bạn">
          {tiles.length === 0 && <span className="muted">Chọn từ để ghép thành câu.</span>}
          {tiles.map((tile, position) => <Button key={tile} onClick={() => setTiles(current => current.filter((_, index) => index !== position))}
            aria-label={'Bỏ từ ' + card.tiles[tile]}><Hanzi text={card.tiles[tile]} linked={false} /></Button>)}
        </div>
        <div className="choices">
          {card.tiles.map((tile, tileIndex) => <Button key={tileIndex} disabled={tiles.includes(tileIndex)}
            onClick={() => setTiles(current => [...current, tileIndex])}><Hanzi text={tile} linked={false} /></Button>)}
        </div>
        <Button variant="primary" disabled={tiles.length !== card.tiles.length || !tiles.length}
          onClick={() => void submit(tiles.map(tile => card.tiles[tile]).join(''))}>Kiểm tra thứ tự</Button>
      </div>}

      {!revealed && mode === 'reverse' && <form className="exercise" onSubmit={submitTyped}>
        <h2>{card.prompt}</h2>
        {card.grammar_hint && <p className="grammar-hint"><Lightbulb size={18} /><Hanzi text={card.grammar_hint} mixed /></p>}
        <label>Viết câu tiếng Trung
          <textarea lang="zh-Hans" value={input} onChange={event => setInput(event.target.value)} rows={3} maxLength={500} />
        </label>
        {card.tiles.length > 0 && <div className="choices">
          {card.tiles.map((tile, index) => <Button key={index} onClick={() => setInput(value => value + tile)}><Hanzi text={tile} linked={false} /></Button>)}
        </div>}
        <Button type="submit" variant="primary" disabled={!input.trim() || busy}>{busy ? 'Đang chấm câu…' : 'Chấm câu'}</Button>
      </form>}

      {revealed && <div className="revealed-face">
        {correct !== null && <p className={'answer-result ' + (correct ? 'answer-correct' : 'answer-incorrect')}>
          {correct ? <Check size={18} /> : <X size={18} />}{correct ? 'Đúng rồi' : 'Cùng xem lại đáp án'}
        </p>}
        <Hanzi className={'focus-hanzi' + (listening || mode === 'confusable' ? ' transcript' : '')} text={card.hanzi || card.answer} />
        <Pinyin text={card.pinyin} visible={pinyinVisible} />
        {card.answer && card.answer !== card.hanzi && mode === 'cloze' && <div className="detail-line"><strong>Từ cần điền</strong><Hanzi text={card.answer} /></div>}
        {card.han_viet && <div className="detail-line"><strong>Âm Hán Việt</strong><span>{card.han_viet}</span></div>}
        {card.meaning_vi && <p className="answer-meaning">{card.meaning_vi}</p>}
        {card.usage_note_vi && <p className="muted">{card.usage_note_vi}</p>}
        {card.mnemonic_vi && <p className="mnemonic">{card.mnemonic_vi}</p>}
        {feedback && <div className="feedback">
          <strong>{feedback.score}/100</strong>
          <p>{feedback.feedback_vi}</p>
          {feedback.corrections.map((entry, index) => <div className="correction" key={index}>
            <div className="actions"><del><Hanzi text={entry.original} /></del><Hanzi text={entry.correction} /></div>
            <p>{entry.explanation_vi}</p>
          </div>)}
          <p><strong>Câu tự nhiên hơn</strong></p>
          <Hanzi text={feedback.corrected_hanzi} />
        </div>}
        {card.characters.length > 0 && <details className="characters-details">
          <summary>Chiết tự và mẹo nhớ</summary>
          {card.characters.map((character, position) => <div className="definition" key={character.char + '-' + position}>
            <Hanzi text={character.char} /><CharacterDetails character={character} pinyinVisible={pinyinVisible} />
          </div>)}
        </details>}
        <div className="actions">
          {card.item_type === 'word' && <EditKnowledgeButton kind="word" id={card.item_id} onSaved={onWordSaved} />}
          {card.item_type === 'pattern' && <EditKnowledgeButton kind="pattern" id={card.item_id} onSaved={onPatternSaved} />}
          {card.sentence_id !== null && <EditKnowledgeButton kind="sentence" id={card.sentence_id} onSaved={onSentenceSaved} />}
        </div>
      </div>}

      {!revealed && mode !== 'flashcard' && <Button className="reveal-button" variant="quiet" disabled={busy} onClick={flip}><Eye size={18} />Xem đáp án</Button>}
      <ErrorNotice message={error} />
      {audio.error && <p className="muted" role="status">{audio.error}</p>}
    </Panel>

    {revealed && <>
      <div className="rating-grid" aria-label="Bạn nhớ thẻ này thế nào?">
        {ratingOptions.map(option => <Button key={option.value} className={'rating rating-' + option.value}
          disabled={ratingDisabled} onClick={() => onRate(option.value, performance.now() - started.current)}>
          <kbd>{option.value}</kbd>{option.label}
        </Button>)}
      </div>
      <ExampleSentences card={card} pinyinOverride={pinyin} onSentenceSaved={onSentenceSaved} />
    </>}

    <div className="keyboard-guide" aria-label="Phím tắt">
      <span><kbd>Space</kbd> Xem đáp án</span><span><kbd>R</kbd> Nghe lại</span>
      <span><kbd>P</kbd> Pinyin</span><span><kbd>1–4</kbd> Mức độ nhớ</span>
    </div>
  </>
}

function pairLines(value: string): [string, string] {
  const [first = '', second = ''] = value.split('\n')
  return [first, second]
}

function ExampleSentences({ card, pinyinOverride, onSentenceSaved }: {
  card: Card
  pinyinOverride: boolean | null
  onSentenceSaved: (sentence: Sentence) => void
}) {
  const [generated, setGenerated] = useState<Sentence[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const canGenerate = card.item_type === 'word' || card.item_type === 'pattern'
  if (card.sentences.length === 0 && !canGenerate) return null

  async function generate() {
    setBusy(true)
    setError('')
    try {
      const result = await api<{ sentences: Sentence[] }>('/ai/examples', { body: { item_type: card.item_type, item_id: card.item_id } })
      setGenerated(current => [...new Map([...current, ...result.sentences].map(sentence => [sentence.id, sentence])).values()])
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  const sentences = [...new Map([...card.sentences, ...generated].map(sentence => [sentence.id, sentence])).values()]

  return <Panel title="Câu ví dụ">
    {sentences.length > 0 && <div className="example-list">
      {sentences.map(sentence => <div className="example-row" key={sentence.id}>
        <div>
          <Hanzi text={sentence.hanzi} />
          <Pinyin text={sentence.pinyin} visible={pinyinOverride ?? undefined} />
          <p>{sentence.meaning_vi}</p>
        </div>
        <div className="actions example-actions">
          <Speaker text={sentence.hanzi} />
          <EditKnowledgeButton kind="sentence" id={sentence.id} label="Sửa câu" onSaved={updated => {
            setGenerated(current => current.map(item => item.id === updated.id ? updated : item))
            onSentenceSaved(updated)
          }} />
        </div>
      </div>)}
    </div>}
    <ErrorNotice message={error} />
    {generated.length > 0 && <Notice>Đã lưu câu mới vào kho.</Notice>}
    {canGenerate && <Button disabled={busy} onClick={() => void generate()}><Sparkles size={18} />{busy ? 'Đang tạo câu…' : 'Tạo câu ví dụ mới (i+1)'}</Button>}
  </Panel>
}
