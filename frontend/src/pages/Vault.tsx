import { useEffect, useState } from 'react'
import { Plus, Search, TreePine } from 'lucide-react'
import { Hanzi, useExperience, WordDefinition } from '../components/Experience'
import { Button, Empty, ErrorNotice, LevelBadge, Loading, PageTitle, Pager, Panel, StatusBadge } from '../components/ui'
import { useResource } from '../hooks/useResource'
import { errorMessage, queueItems, withQuery } from '../lib/api'
import type { PageResult, Word } from '../types'

const pageSize = 24

export function Vault() {
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
    <PageTitle title="Từ điển và Cây chữ" description="Tra từ trong kho và khám phá những từ có chung một chữ." />
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
            {(!status || status === 'ignored') && <Button disabled={queueing !== null} onClick={() => void add(word)}><Plus size={18} />Thêm vào hàng đợi ôn</Button>}
          </div>}
        </article>
      })}
      <Pager offset={offset} limit={pageSize} total={resource.data.total} onChange={setOffset} />
    </Panel>}
  </div>
}
