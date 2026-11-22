import { useEffect, useState } from 'react'
import { Plus, Search, TreePine } from 'lucide-react'
import { Hanzi, Pinyin, useExperience, WordDefinition } from '../components/Experience'
import { EditKnowledgeButton } from '../components/KnowledgeEditor'
import { Button, Empty, ErrorNotice, LevelBadge, Loading, PageTitle, Pager, Panel, Speaker, StatusBadge } from '../components/ui'
import { useResource } from '../hooks/useResource'
import { errorMessage, queueItems, withQuery } from '../lib/api'
import type { PageResult, Pattern, Sentence, Word } from '../types'

const pageSize = 24

export function Vault() {
  const [section, setSection] = useState<'words' | 'patterns' | 'sentences'>('words')
  return <div className="page-stack">
    <PageTitle title="Từ điển và Cây chữ" description="Tra từ, khám phá cây chữ và chỉnh nội dung trong kho." />
    <div className="actions" aria-label="Loại mục trong kho">
      <Button aria-pressed={section === 'words'} onClick={() => setSection('words')}>Từ vựng</Button>
      <Button aria-pressed={section === 'patterns'} onClick={() => setSection('patterns')}>Mẫu ngữ pháp</Button>
      <Button aria-pressed={section === 'sentences'} onClick={() => setSection('sentences')}>Câu ví dụ</Button>
    </div>
    {section === 'words' && <VaultWords />}
    {section === 'patterns' && <VaultPatterns />}
    {section === 'sentences' && <VaultSentences />}
  </div>
}

function VaultWords() {
  const { notify, showCharacter } = useExperience()
  const [query, setQuery] = useState('')
  const [term, setTerm] = useState('')
  const [level, setLevel] = useState('')
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [queueing, setQueueing] = useState<number | null>(null)
  const [queued, setQueued] = useState<number[]>([])
  const [error, setError] = useState('')
  const resource = useResource<PageResult<Word>>(withQuery('/vault/words', { q: term, level, offset, limit: pageSize }))
  const singleHanzi = /^\p{Script=Han}$/u.test(query.trim())

  useEffect(() => {
    const timeout = setTimeout(() => { setTerm(query.trim()); setOffset(0) }, 180)
    return () => clearTimeout(timeout)
  }, [query])

  async function add(word: Word) {
    setQueueing(word.id)
    setError('')
    try {
      await queueItems('word', [word.id])
      setQueued(current => [...current, word.id])
      notify('Đã thêm “' + word.simplified + '” vào hàng đợi ôn.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setQueueing(null)
    }
  }

  return <div className="page-stack">
    <Panel className="vault-controls">
      <div className="form-grid">
        <label>Tìm trong kho
          <span className="search-input"><Search size={18} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Hán tự, Pinyin hoặc nghĩa tiếng Việt" /></span>
        </label>
        <label>Cấp độ
          <select value={level} onChange={event => { setLevel(event.target.value); setOffset(0) }}>
            <option value="">Mọi cấp độ</option>
            {[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>HSK {value}</option>)}
            <option value="0">Mở rộng</option>
          </select>
        </label>
        {singleHanzi && <Button onClick={() => showCharacter(query.trim())}><TreePine size={18} />Mở cây chữ</Button>}
      </div>
    </Panel>
    <ErrorNotice message={error} />
    {resource.loading && <Loading label="Đang tìm từ…" />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data && <Panel title={'Kho từ · ' + resource.data.total.toLocaleString('vi-VN') + ' từ'}>
      {resource.data.items.length === 0 && <Empty>Chưa có từ phù hợp với tìm kiếm của bạn.</Empty>}
      {resource.data.items.map(word => {
        const status = queued.includes(word.id) ? 'new' : word.status
        const isOpen = expanded === word.id
        return <article className="vault-word" key={word.id}>
          <div className="vault-word-row">
            <div className="vault-word-label"><Hanzi text={word.simplified} /><span>{word.pinyin}</span></div>
            <p>{word.meaning_vi}</p>
            <div className="vault-tags"><LevelBadge level={word.hsk_level} /><StatusBadge status={status} /></div>
            <Button variant="quiet" aria-expanded={isOpen} onClick={() => setExpanded(isOpen ? null : word.id)}>{isOpen ? 'Thu gọn' : 'Xem từ'}</Button>
          </div>
          {isOpen && <div className="vault-word-detail">
            <WordDefinition word={word} />
            {word.traditional && word.traditional !== word.simplified && <div className="detail-line"><strong>Phồn thể</strong><Hanzi text={word.traditional} /></div>}
            <div className="actions">
              {!status && <Button disabled={queueing !== null} onClick={() => void add(word)}><Plus size={18} />Thêm vào hàng đợi ôn</Button>}
              <EditKnowledgeButton kind="word" id={word.id} onSaved={updated => {
                setQueued(current => current.filter(id => id !== updated.id))
                resource.setData(current => current && ({ ...current, items: current.items.map(item => item.id === updated.id ? updated : item) }))
              }} />
            </div>
          </div>}
        </article>
      })}
      <Pager offset={offset} limit={pageSize} total={resource.data.total} onChange={setOffset} />
    </Panel>}
  </div>
}

function VaultPatterns() {
  return <VaultRecords<Pattern> path="/patterns" searchLabel="Tìm mẫu ngữ pháp" empty="Chưa có mẫu ngữ pháp phù hợp."
    render={(pattern, save) => <>
      <div className="split">
        <h3>{pattern.title_vi}</h3>
        <LevelBadge level={pattern.hsk_level} />
      </div>
      <Hanzi text={pattern.pattern_formula} className="vault-record-hanzi" mixed />
      <p>{pattern.explanation_vi}</p>
      {pattern.structure_notes_vi && <p className="muted">{pattern.structure_notes_vi}</p>}
      <EditKnowledgeButton kind="pattern" id={pattern.id} onSaved={save} />
    </>} />
}

function VaultSentences() {
  return <VaultRecords<Sentence> path="/sentences" searchLabel="Tìm câu ví dụ" empty="Chưa có câu ví dụ phù hợp."
    render={(sentence, save) => <>
      <div className="split">
        <Hanzi text={sentence.hanzi} className="vault-record-hanzi" />
        <Speaker text={sentence.hanzi} />
      </div>
      <Pinyin text={sentence.pinyin} />
      <p>{sentence.meaning_vi}</p>
      <EditKnowledgeButton kind="sentence" id={sentence.id} onSaved={save} />
    </>} />
}

function VaultRecords<T extends { id: number }>({ path, searchLabel, empty, render }: {
  path: string
  searchLabel: string
  empty: string
  render: (record: T, save: (updated: T) => void) => React.ReactNode
}) {
  const [query, setQuery] = useState('')
  const [term, setTerm] = useState('')
  const [offset, setOffset] = useState(0)
  const resource = useResource<PageResult<T>>(withQuery(path, { q: term, offset, limit: pageSize }))

  useEffect(() => {
    const timeout = setTimeout(() => { setTerm(query.trim()); setOffset(0) }, 180)
    return () => clearTimeout(timeout)
  }, [query])

  return <div className="page-stack">
    <Panel>
      <label>{searchLabel}<span className="search-input">
        <Search size={18} /><input maxLength={100} value={query} onChange={event => setQuery(event.target.value)} />
      </span></label>
    </Panel>
    {resource.loading && <Loading />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data && <Panel>
      {resource.data.items.length === 0 && <Empty>{empty}</Empty>}
      {resource.data.items.map(record => <article className="vault-record" key={record.id}>
        {render(record, updated => resource.setData(current => current && ({
          ...current,
          items: current.items.map(item => item.id === updated.id ? updated : item),
        })))}
      </article>)}
      <Pager offset={offset} limit={pageSize} total={resource.data.total} onChange={setOffset} />
    </Panel>}
  </div>
}
