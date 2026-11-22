import { useState } from 'react'
import { Flame, Plus, Settings2, Target } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Hanzi, useExperience } from '../components/Experience'
import { BackupPanel } from '../components/BackupPanel'
import { Button, Empty, ErrorNotice, Loading, PageTitle, Pager, Panel, StatusBadge } from '../components/ui'
import { useResource } from '../hooks/useResource'
import { api, errorMessage, queueItems, withQuery } from '../lib/api'
import type { Dashboard, Health, HskLevel, PageResult, Word } from '../types'
import { PaceNote } from './Home'

const gapPageSize = 24
const loadHealth = (path: string, signal: AbortSignal) => api<Health>(path, { signal, acceptStatus: 503 })

export function Progress() {
  const resource = useResource<Dashboard>('/dashboard')
  const [level, setLevel] = useState<number | null>(null)
  return <div className="page-stack">
    <PageTitle title="Tiến độ HSK" />
    {resource.loading && <Loading />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data && <>
      <Panel>
        <div className="section-heading"><Target size={23} /><h2>Nhịp học 7 ngày</h2></div>
        <PaceNote pace={resource.data.pace} />
      </Panel>
      <Panel title="Bản đồ từ vựng HSK 1–5">
        <div className="coverage-legend"><span className="legend-mastered">Đã thuộc</span>
          <span className="legend-ingested">Đã nạp từ tài liệu</span><span>Tổng mục tiêu HSK</span></div>
        <div className="coverage-list">
          {resource.data.levels.map(entry => <Coverage key={entry.level} level={entry} active={entry.level === level}
            onClick={() => setLevel(current => current === entry.level ? null : entry.level)} />)}
        </div>
      </Panel>
      {level !== null && <GapFiller key={level} level={level} />}
      <Panel>
        <div className="split board-title">
          <div className="section-heading"><Flame size={23} /><h2>Từ hay sai</h2></div>
          {resource.data.leeches.length > 0 && <Link className="button button-primary" to="/hoc?leeches=true&size=10">Ôn gấp các từ hay sai</Link>}
        </div>
        {resource.data.leeches.length === 0 && <Empty>Các từ cần ôn thêm sẽ xuất hiện ở đây.</Empty>}
        {resource.data.leeches.map(word => <div className="leech-row" key={word.card_id}>
          <div><Hanzi text={word.simplified} /><span className="muted">{word.meaning_vi}</span></div>
          <span className="status status-learning">{word.wrong_count} lần sai</span>
        </div>)}
      </Panel>
    </>}
    <PreferencesPanel onRestored={resource.reload} />
  </div>
}

function Coverage({ level, active, onClick }: { level: HskLevel; active: boolean; onClick: () => void }) {
  const target = Math.max(1, level.total)
  return <article className="coverage-row">
    <h3>HSK {level.level}</h3>
    <div className="coverage-bars">
      <div><progress max={target} value={level.mastered} className="mastered-bar" aria-label={'HSK ' + level.level + ' đã thuộc'} /><span>{level.mastered}</span></div>
      <div><progress max={target} value={level.ingested} className="ingested-bar" aria-label={'HSK ' + level.level + ' đã nạp từ tài liệu'} /><span>{level.ingested}</span></div>
    </div>
    <strong className="coverage-total">{level.total.toLocaleString('vi-VN')} từ</strong>
    <Button aria-expanded={active} onClick={onClick}>{active ? 'Ẩn từ còn thiếu' : 'Xem từ còn thiếu'}</Button>
  </article>
}

function GapFiller({ level }: { level: number }) {
  const { notify } = useExperience()
  const [offset, setOffset] = useState(0)
  const [queued, setQueued] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const resource = useResource<PageResult<Word>>(withQuery('/dashboard/gaps/' + level, { offset, limit: gapPageSize }))
  const pending = resource.data?.items.filter(word => (!word.status || word.status === 'ignored') && !queued.includes(word.id)) ?? []

  async function add(words: Word[]) {
    if (!words.length || busy) return
    setBusy(true)
    setError('')
    try {
      const ids = words.map(word => word.id)
      const result = await queueItems('word', ids)
      setQueued(current => [...current, ...ids])
      notify('Đã thêm ' + result.queued + ' từ vào hàng đợi ôn.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  return <Panel className="gap-panel">
    <div className="split">
      <h2>Từ HSK {level} chưa gặp trong tài liệu</h2>
      <Button variant="primary" disabled={busy || !pending.length} onClick={() => void add(pending)}><Plus size={17} />Thêm cả trang vào hàng đợi</Button>
    </div>
    {resource.loading && <Loading />}
    <ErrorNotice message={resource.error} retry={resource.reload} />
    <ErrorNotice message={error} />
    {resource.data?.items.length === 0 && <Empty>Chưa có từ nào còn thiếu trong danh sách đã nạp.</Empty>}
    {resource.data && <div className="gap-words">
      {resource.data.items.map(word => {
        const status = queued.includes(word.id) ? 'new' : word.status
        return <div className="gap-word" key={word.id}>
          <div><Hanzi text={word.simplified} /><span>{word.meaning_vi}</span></div>
          {status && status !== 'ignored' ? <StatusBadge status={status} /> : <Button className="icon-button" aria-label={'Thêm ' + word.simplified + ' vào kho ôn'}
            disabled={busy} onClick={() => void add([word])}><Plus size={18} /></Button>}
        </div>
      })}
      <Pager offset={offset} limit={gapPageSize} total={resource.data.total} onChange={setOffset} />
    </div>}
  </Panel>
}

function PreferencesPanel({ onRestored }: { onRestored: () => void }) {
  const { preferences, toggleTheme, togglePinyin, flushPreferences, preferenceError } = useExperience()
  const resource = useResource<Health>('/health', loadHealth)
  const [geminiCheck, setGeminiCheck] = useState('')
  const [geminiError, setGeminiError] = useState('')
  const [checking, setChecking] = useState(false)

  async function checkGemini() {
    if (checking) return
    setChecking(true)
    setGeminiError('')
    setGeminiCheck('')
    try {
      const ready = await api<{ status: 'ok'; model: string }>('/health/gemini', { body: {} })
      setGeminiCheck('Gemini đã phản hồi bằng mô hình ' + ready.model + '.')
    } catch (cause) {
      setGeminiError(errorMessage(cause))
    } finally {
      setChecking(false)
    }
  }

  return <><Panel>
    <div className="section-heading"><Settings2 size={23} /><h2>Cài đặt</h2></div>
    <div className="setting-row">
      <div><h3 id="pinyin-setting">Hiện Pinyin mặc định</h3><p>Áp dụng cho thẻ, câu ví dụ và trình đọc.</p></div>
      <Button className="switch" role="switch" aria-checked={preferences.pinyin} aria-labelledby="pinyin-setting" onClick={togglePinyin}><span /></Button>
    </div>
    <div className="setting-row">
      <div><h3 id="theme-setting">Giao diện tối</h3></div>
      <Button className="switch" role="switch" aria-checked={preferences.theme === 'dark'} aria-labelledby="theme-setting" onClick={toggleTheme}><span /></Button>
    </div>
    <ErrorNotice message={preferenceError && 'Chưa đồng bộ được cài đặt. ' + preferenceError}
      retry={() => { void flushPreferences().catch(() => {}) }} />
    <div className="setting-row">
      <div><h3>Cơ sở dữ liệu</h3>
        {resource.data && <p>
          {resource.data.hsk_word_count?.toLocaleString('vi-VN') ?? '—'} từ HSK · {resource.data.tts_cache_count?.toLocaleString('vi-VN') ?? '—'} tệp âm thanh đã lưu
        </p>}
      </div>
      {resource.data && <span className={'status ' + (resource.data.database === 'ok' ? 'status-mastered' : 'status-learning')}>
        {resource.data.database === 'ok' ? 'Đang kết nối' : 'Mất kết nối'}
      </span>}
      {resource.error && <span className="status status-unknown">Chưa kiểm tra được</span>}
    </div>
    {!resource.loading && !resource.error && <Button variant="quiet" onClick={resource.reload}>Kiểm tra lại hệ thống</Button>}
    <div className="setting-row">
      <div><h3>Gemini</h3>
        {resource.data && <p>{resource.data.gemini_configured ? resource.data.gemini_model : 'Thêm GEMINI_API_KEY vào tệp .env của máy chủ để bật trích xuất và chấm bài.'}</p>}
      </div>
      {resource.loading && <Loading />}
      {resource.data && <span className={'status ' + (resource.data.gemini_configured ? 'status-mastered' : 'status-unknown')}>{resource.data.gemini_configured ? 'Đã cấu hình' : 'Chưa cấu hình'}</span>}
    </div>
    <ErrorNotice message={resource.error} retry={resource.reload} />
    {resource.data?.gemini_configured && <Button disabled={checking} onClick={() => void checkGemini()}>
      {checking ? 'Đang kiểm tra…' : 'Kiểm tra Gemini'}
    </Button>}
    {geminiCheck && <p role="status">{geminiCheck}</p>}
    <ErrorNotice message={geminiError} />
  </Panel>
    <BackupPanel onRestored={() => { onRestored(); resource.reload() }} />
  </>
}
