import { useState } from 'react'
import type { FormEvent } from 'react'
import { BookOpenText, Check, GitCompareArrows, PencilLine, RefreshCw, Sparkles } from 'lucide-react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { Hanzi, useExperience } from '../components/Experience'
import { PairClozeQuestions } from '../components/PairClozeQuestions'
import { Button, Empty, ErrorNotice, Loading, PageTitle, Panel } from '../components/ui'
import { useResource } from '../hooks/useResource'
import { api, errorMessage, queueItems, withQuery } from '../lib/api'
import type { PageResult, Pair, StoryAttempt, Word } from '../types'
import { Reader } from './Reader'

const tools = [
  { route: '/luyen-hsk/cap-tu', title: 'Cặp từ dễ nhầm', description: 'Phân biệt sắc thái qua hai câu điền từ.', icon: GitCompareArrows },
  { route: '/luyen-hsk/viet-truyen', title: '5 từ thành truyện', description: 'Luyện viết đoạn văn ngắn theo dạng bài HSK 5.', icon: PencilLine },
  { route: '/luyen-hsk/trinh-doc', title: 'Trình đọc', description: 'Đọc đoạn tiếng Trung và tra từ ngay trong câu.', icon: BookOpenText },
]

export function Tools() {
  return <div className="page-stack">
    <PageTitle title="Luyện HSK 4–5" />
    <nav className="tool-nav" aria-label="Các bài luyện HSK">
      {tools.map(({ route, title, icon: Icon }) => <NavLink key={route} to={route}>
        <Icon size={19} />{title}
      </NavLink>)}
    </nav>
    <Routes>
      <Route index element={<div className="tool-grid">
        {tools.map(({ route, title, description, icon: Icon }) => <Link className="panel tool-card" key={route} to={route}>
          <span className="feature-icon"><Icon size={23} /></span><h2>{title}</h2><p>{description}</p>
        </Link>)}
      </div>} />
      <Route path="cap-tu" element={<Confusables />} />
      <Route path="viet-truyen" element={<Story />} />
      <Route path="trinh-doc" element={<Reader />} />
      <Route path="*" element={<Panel><Empty>Không tìm thấy bài luyện này.</Empty><Link className="text-link" to="/luyen-hsk">Về Luyện HSK 4–5</Link></Panel>} />
    </Routes>
  </div>
}

function Confusables() {
  const resource = useResource<Pair[]>('/ai/confusables')
  const { notify } = useExperience()
  const [selectedPair, setSelectedPair] = useState<number | null>(null)
  const [customPairs, setCustomPairs] = useState<Pair[]>([])
  const [wordA, setWordA] = useState<Word | null>(null)
  const [wordB, setWordB] = useState<Word | null>(null)
  const [busy, setBusy] = useState(false)
  const [queued, setQueued] = useState<number[]>([])
  const [queueing, setQueueing] = useState(false)
  const [error, setError] = useState('')
  const pairs = [...new Map([...(resource.data ?? []), ...customPairs].map(pair => [pair.id, pair])).values()]
  const pair = pairs.find(value => value.id === selectedPair) ?? pairs[0]

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!wordA || !wordB || wordA.id === wordB.id) return
    setBusy(true)
    setError('')
    try {
      const result = await api<Pair>('/ai/confusables', { body: { word_a_id: wordA.id, word_b_id: wordB.id } })
      setCustomPairs(current => [...current, result])
      setSelectedPair(result.id)
      notify('Đã tạo cặp từ để luyện.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  async function queuePair() {
    if (!pair) return
    setQueueing(true)
    setError('')
    try {
      await queueItems('confusable', [pair.id])
      setQueued(current => [...current, pair.id])
      notify('Đã thêm cặp từ vào hàng đợi ôn.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setQueueing(false)
    }
  }

  return <div className="page-stack">
    <Panel title="Cặp từ dễ nhầm">
      {resource.loading && <Loading />}
      <ErrorNotice message={resource.error} retry={resource.reload} />
      {resource.data?.length === 0 && !pair && <Empty>Chưa có cặp từ nào trong kho.</Empty>}
      {pair && <>
        <label className="pair-select">Chọn cặp từ
          <select value={pair.id} onChange={event => setSelectedPair(Number(event.target.value))}>
            {pairs.map(value => <option key={value.id} value={value.id}>{value.word_a} / {value.word_b}</option>)}
          </select>
        </label>
        <PairExercise key={pair.id} pair={pair} />
        <Button variant="quiet" className="mt-3" disabled={queueing || queued.includes(pair.id)} onClick={() => void queuePair()}>
          {queued.includes(pair.id) ? 'Đã thêm vào hàng đợi ôn' : 'Thêm cặp từ vào hàng đợi ôn'}
        </Button>
      </>}
    </Panel>

    <Panel title="Tạo cặp từ của bạn">
      <form className="page-stack" onSubmit={event => void generate(event)}>
        <div className="form-grid">
          <WordPicker label="Từ thứ nhất" selected={wordA} other={wordB?.id} onPick={setWordA} />
          <WordPicker label="Từ thứ hai" selected={wordB} other={wordA?.id} onPick={setWordB} />
        </div>
        <div className="actions"><Button type="submit" variant="primary" disabled={busy || !wordA || !wordB}><Sparkles size={18} />{busy ? 'Đang phân tích…' : 'So sánh bằng Gemini'}</Button></div>
      </form>
      <ErrorNotice message={error} />
    </Panel>
  </div>
}

function PairExercise({ pair }: { pair: Pair }) {
  return <div className="pair-exercise">
    <div className="pair-word-heading"><Hanzi text={pair.word_a} /><span>/</span><Hanzi text={pair.word_b} /></div>
    <p><Hanzi text={pair.diff_explanation_vi} mixed /></p>
    <PairClozeQuestions prompts={[pair.cloze_a_hanzi, pair.cloze_b_hanzi]}
      choices={[pair.word_a, pair.word_b]} correct={[pair.cloze_a_answer, pair.cloze_b_answer]} />
  </div>
}

function WordPicker({ label, selected, other, onPick }: { label: string; selected: Word | null; other?: number; onPick: (word: Word | null) => void }) {
  const [query, setQuery] = useState('')
  const resource = useResource<PageResult<Word>>(query.trim() && !selected ? withQuery('/vault/words', { q: query.trim(), limit: 6 }) : null)
  return <div className="word-picker">
    <label>{label}<input value={selected?.simplified ?? query} placeholder="Tìm từ trong kho"
      onChange={event => {
        onPick(null)
        setQuery(event.target.value)
      }} /></label>
    {!selected && query.trim() && <div className="picker-results">
      {resource.loading && <Loading />}
      <ErrorNotice message={resource.error} />
      {resource.data?.items.length === 0 && <Empty>Chưa có từ phù hợp.</Empty>}
      {resource.data?.items.map(word => <Button className="picker-result" key={word.id} variant="quiet" disabled={word.id === other} onClick={() => onPick(word)}>
        <Hanzi text={word.simplified} linked={false} /><span>{word.meaning_vi}</span>
      </Button>)}
    </div>}
  </div>
}

function Story() {
  const targets = useResource<{ words: string[] }>('/ai/story/words')
  const history = useResource<StoryAttempt[]>('/ai/story')
  const { notify } = useExperience()
  const [text, setText] = useState('')
  const [attempt, setAttempt] = useState<StoryAttempt | null>(null)
  const [openAttempt, setOpenAttempt] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const count = Array.from(text).filter(character => !/\s/u.test(character)).length
  const words = targets.data?.words ?? []
  const matched = words.filter(word => text.includes(word)).length

  function reroll() {
    setAttempt(null)
    setError('')
    targets.reload()
  }

  async function grade(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!text.trim() || words.length !== 5 || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await api<StoryAttempt>('/ai/story', { body: { target_words: words, text: text.trim() } })
      setAttempt(result)
      history.reload()
      notify('Đã lưu bài viết vào lịch sử.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  const previous = history.data?.find(item => item.id === openAttempt)
  return <div className="page-stack">
    <Panel title="5 từ thành truyện">
      <p>Viết một đoạn tiếng Trung khoảng 60–100 chữ và dùng cả 5 từ dưới đây.</p>
      {targets.loading && <Loading label="Đang chọn từ…" />}
      <ErrorNotice message={targets.error} retry={targets.reload} />
      {words.length === 5 && <form className="page-stack" onSubmit={event => void grade(event)}>
        <div className="target-list" aria-label={'Đã dùng ' + matched + ' trên 5 từ'}>
          {words.map(word => <span key={word} className={'target-word' + (text.includes(word) ? ' target-used' : '')}>
            {text.includes(word) && <Check size={18} aria-label="Đã dùng" />}<Hanzi text={word} />
          </span>)}
        </div>
        <div>
          <label>Đoạn văn của bạn
            <textarea lang="zh-Hans" className="story-input" value={text} maxLength={2000} rows={6} onChange={event => setText(event.target.value)} />
          </label>
          <div className="split count-line"><span>{matched}/5 từ đã dùng</span><span>{count} chữ</span></div>
        </div>
        <div className="actions">
          <Button variant="primary" type="submit" disabled={!text.trim() || busy}><Sparkles size={18} />{busy ? 'Đang chấm bài…' : 'Chấm bài viết'}</Button>
          <Button disabled={busy} onClick={reroll}><RefreshCw size={18} />Đổi bộ từ</Button>
        </div>
      </form>}
      {targets.data && words.length !== 5 && <Empty>Chưa đủ 5 từ HSK 4–5 để tạo đề.</Empty>}
      <ErrorNotice message={error} />
    </Panel>
    {attempt && <StoryFeedback attempt={attempt} title="Kết quả bài vừa chấm" />}

    <Panel title="Lịch sử bài viết">
      {history.loading && <Loading />}
      <ErrorNotice message={history.error} retry={history.reload} />
      {history.data?.length === 0 && <Empty>Bài viết đã chấm sẽ được lưu ở đây.</Empty>}
      {history.data?.map(item => <div className="story-history-row" key={item.id}>
        <div><Hanzi text={item.target_words.join(' · ')} /><span className="muted">{new Date(item.created_at).toLocaleDateString('vi-VN')}</span></div>
        <Button aria-expanded={openAttempt === item.id} onClick={() => setOpenAttempt(openAttempt === item.id ? null : item.id)}>
          {item.score}/100 · {openAttempt === item.id ? 'Thu gọn' : 'Xem bài'}
        </Button>
      </div>)}
    </Panel>
    {previous && <StoryFeedback attempt={previous} title="Bài viết đã lưu" showText />}
  </div>
}

function StoryFeedback({ attempt, title, showText }: { attempt: StoryAttempt; title: string; showText?: boolean }) {
  return <Panel>
    <div className="split score-heading"><h2>{title}</h2><strong>{attempt.score}/100</strong></div>
    {showText && <p className="story-text"><Hanzi text={attempt.text} /></p>}
    <div className="feedback-sections">
      <section><h3>Cách dùng từ</h3>
        {attempt.feedback.usage.map(entry => <div className="usage-row" key={entry.word}>
          <span className={'status ' + (entry.correct ? 'status-mastered' : 'status-learning')}>{entry.correct ? 'Dùng đúng' : 'Cần xem lại'}</span>
          <Hanzi text={entry.word} /><p>{entry.feedback_vi}</p>
        </div>)}
      </section>
      <section><h3>Ngữ pháp</h3><p>{attempt.feedback.grammar_vi}</p></section>
      <section><h3>Độ tự nhiên</h3><p>{attempt.feedback.naturalness_vi}</p></section>
      <section className="feedback"><h3>Đoạn viết gợi ý</h3><Hanzi text={attempt.feedback.rewrite_hanzi} /></section>
    </div>
  </Panel>
}
