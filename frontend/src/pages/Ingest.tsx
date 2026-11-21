import { useEffect, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { ClipboardPaste, FileText, HardDriveUpload, Save, UploadCloud } from 'lucide-react'
import { useExperience } from '../components/Experience'
import { Button, Empty, ErrorNotice, LevelBadge, Loading, PageTitle, Panel } from '../components/ui'
import { useResource } from '../hooks/useResource'
import { api, errorMessage, withQuery } from '../lib/api'
import type { Source, SourceType, StagedPattern, StagedSentence, StagedWord, Staging } from '../types'

const accepted = '.png,.jpg,.jpeg,.webp,.pdf,.pptx,.ppt,.docx,.doc,.xlsx,.csv,.txt'
const acceptedSet = new Set(accepted.split(','))
const sourceLabels: Record<SourceType, string> = {
  image: 'Ảnh', pdf: 'PDF', pptx: 'Trang chiếu', docx: 'Văn bản',
  xlsx: 'Bảng tính', text: 'Tệp văn bản', paste: 'Văn bản đã dán',
}

const rows = [
  ['words', 'Từ vựng'],
  ['grammar_patterns', 'Mẫu ngữ pháp'],
  ['sentences', 'Câu ví dụ'],
] as const
type Group = typeof rows[number][0]
const rowKey = (group: Group, index: number) => group + '-' + index

function dateLabel(isoDate: string) {
  const date = new Date(isoDate)
  return Number.isNaN(date.getTime()) ? '' : Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium' }).format(date)
}

export function Ingest() {
  const sources = useResource<Source[]>('/ingestion/sources')
  const { notify } = useExperience()
  const [staging, setStaging] = useState<Staging | null>(null)
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set())
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [pasted, setPasted] = useState('')
  const [dragging, setDragging] = useState(false)
  const picker = useRef<HTMLInputElement>(null)
  const stagingTitle = useRef<HTMLHeadingElement>(null)
  const extractRef = useRef<(input: File | string) => void>()

  async function extract(input: File | string) {
    if (inFlight.current || staging) return
    setError('')
    if (typeof input === 'string' && !input.trim()) return
    if (input instanceof File) {
      const extension = input.name.toLowerCase().match(/\.[^.]+$/)?.[0]
      if (!extension || !acceptedSet.has(extension)) {
        setError('Định dạng tệp này chưa được hỗ trợ. Bạn chọn một định dạng trong danh sách bên dưới nhé.')
        return
      }
    }

    inFlight.current = true
    setBusy(true)
    const body = new FormData()
    if (typeof input === 'string') body.append('text', input.trim())
    else body.append('file', input)
    try {
      const result = await api<Staging>('/ingestion/extract', { body })
      setExcluded(new Set())
      setStaging(result)
      setPasted('')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  extractRef.current = input => { void extract(input) }

  useEffect(() => {
    if (staging) {
      stagingTitle.current?.focus()
      return
    }

    function onPaste(event: ClipboardEvent) {
      const clipboard = event.clipboardData
      if (!clipboard || inFlight.current) return
      const image = Array.from(clipboard.items).find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile()
      if (image) {
        event.preventDefault()
        const extension = image.type === 'image/jpeg' ? 'jpg' : image.type === 'image/webp' ? 'webp' : 'png'
        extractRef.current?.(new File([image], 'Ảnh dán.' + extension, { type: image.type }))
        return
      }
      const text = clipboard.getData('text/plain')
      if (text.trim()) {
        event.preventDefault()
        setPasted(text)
        extractRef.current?.(text)
      }
    }

    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [staging !== null])

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) void extract(file)
  }

  function setIncluded(group: Group, index: number, checked: boolean) {
    const key = rowKey(group, index)
    setExcluded(previous => {
      const next = new Set(previous)
      if (checked) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function update<K extends Group>(group: K, index: number, item: Staging[K][number]) {
    setStaging(current => current && ({
      ...current,
      [group]: current[group].map((value, itemIndex) => itemIndex === index ? item : value),
    }))
  }

  async function save() {
    if (!staging || saving) return
    const selected = {
      ...staging,
      title: staging.title.trim(),
      words: staging.words.filter((_, index) => !excluded.has(rowKey('words', index))),
      grammar_patterns: staging.grammar_patterns.filter((_, index) => !excluded.has(rowKey('grammar_patterns', index))),
      sentences: staging.sentences.filter((_, index) => !excluded.has(rowKey('sentences', index))),
    }
    setError('')
    if (!selected.title) {
      setError('Hãy đặt tên cho nguồn tài liệu.')
      return
    }
    if (selected.words.some(word => !word.simplified.trim() || !word.meaning_vi.trim())
      || selected.grammar_patterns.some(pattern => !pattern.pattern_formula.trim() || !pattern.title_vi.trim())
      || selected.sentences.some(sentence => !sentence.hanzi.trim() || !sentence.meaning_vi.trim())) {
      setError('Hãy điền nội dung và nghĩa cho các mục đã chọn.')
      return
    }
    if (!selected.words.length && !selected.grammar_patterns.length && !selected.sentences.length) {
      setError('Hãy chọn ít nhất một mục để lưu.')
      return
    }
    setSaving(true)
    try {
      const source = await api<Source>('/ingestion/save', { body: selected })
      setStaging(null)
      sources.reload()
      notify('Đã lưu “' + source.title + '” vào kho ôn.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setSaving(false)
    }
  }

  const extended = staging?.words.flatMap((word, index) => word.hsk_level === null ? [rowKey('words', index)] : []) ?? []
  const extendedIncluded = extended.some(key => !excluded.has(key))
  const selectedCount = staging ? rows.reduce((total, [group]) =>
    total + staging[group].filter((_, index) => !excluded.has(rowKey(group, index))).length, 0) : 0

  return <div className="page-stack">
    <PageTitle title="Nạp tài liệu" description="Đưa ảnh chụp, trang chiếu hoặc văn bản vào kho ôn." />
    {!staging && <Panel className="upload-panel">
      <div className={'dropzone' + (dragging ? ' drag-active' : '')}
        onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={drop}>
        <span className="feature-icon"><UploadCloud size={25} /></span>
        <h2>Thả tệp vào đây</h2>
        <p>Hoặc nhấn <kbd>Ctrl</kbd> <kbd>V</kbd> để nạp ảnh chụp và văn bản đã sao chép.</p>
        <input type="file" ref={picker} accept={accepted} className="sr-only" aria-label="Chọn tệp tài liệu"
          disabled={busy} onChange={event => {
            const file = event.target.files?.[0]
            if (file) void extract(file)
            event.target.value = ''
          }} />
        <Button variant="primary" onClick={() => picker.current?.click()} disabled={busy}><HardDriveUpload size={19} />Chọn tệp</Button>
        <span className="muted small">Ảnh PNG, JPG, WebP · PDF · PowerPoint · Word · Excel · CSV · TXT</span>
      </div>
      <form className="paste-form" onSubmit={event => { event.preventDefault(); void extract(pasted) }}>
        <label>Văn bản để trích xuất
          <textarea rows={3} value={pasted} onChange={event => setPasted(event.target.value)} placeholder="Gõ văn bản tiếng Trung hoặc dán từ bộ nhớ tạm" disabled={busy} />
        </label>
        <Button type="submit" disabled={busy || !pasted.trim()}><ClipboardPaste size={18} />Trích xuất văn bản</Button>
      </form>
      {busy && <Loading label="Đang đọc tài liệu và trích xuất mục ôn…" />}
      <ErrorNotice message={error} />
    </Panel>}

    {staging && <Panel className="staging">
      <h2 ref={stagingTitle} tabIndex={-1}>Kiểm tra trước khi lưu</h2>
      {staging.notice_vi && <p className="info-strip" role="status">{staging.notice_vi}</p>}
      <div className="form-grid">
        <label>Tên nguồn
          <input value={staging.title} onChange={event => setStaging({ ...staging, title: event.target.value })} maxLength={250} />
        </label>
        <label>Ghi chú nguồn
          <input value={staging.summary_note} onChange={event => setStaging({ ...staging, summary_note: event.target.value })} />
        </label>
      </div>

      {rows.map(([group, title]) => <section className="stage-group" key={group}>
        <div className="split stage-group-title">
          <h3>{title} <span className="muted">({staging[group].length})</span></h3>
          {group === 'words' && extended.length > 0 && <Button variant="quiet" onClick={() =>
            setExcluded(previous => {
              const next = new Set(previous)
              extended.forEach(key => extendedIncluded ? next.add(key) : next.delete(key))
              return next
            })
          }>{extendedIncluded ? 'Bỏ chọn từ mở rộng' : 'Chọn từ mở rộng'}</Button>}
        </div>
        {!staging[group].length ? <Empty>Không có mục nào trong tài liệu này.</Empty>
          : <div className="table-scroll" tabIndex={0} aria-label={title}>
            <table>
              <thead><tr><th scope="col">Lưu</th><th scope="col">{group === 'words' ? 'Từ' : group === 'sentences' ? 'Câu tiếng Trung' : 'Cấu trúc'}</th>
                <th scope="col">{group === 'grammar_patterns' ? 'Tên và giải thích' : 'Nghĩa tiếng Việt'}</th><th scope="col">Chi tiết</th></tr></thead>
              <tbody>
                {staging[group].map((item, index) => <tr key={index}>
                  <td><input className="checkbox" type="checkbox" aria-label={'Lưu mục ' + (index + 1) + ' trong ' + title.toLowerCase()}
                    checked={!excluded.has(rowKey(group, index))}
                    onChange={event => setIncluded(group, index, event.target.checked)} /></td>
                  {group === 'words' && <WordFields word={item as StagedWord} change={word => update('words', index, word)} />}
                  {group === 'grammar_patterns' && <PatternFields pattern={item as StagedPattern} change={pattern => {
                    const previous = item as StagedPattern
                    setStaging(current => current && ({
                      ...current,
                      grammar_patterns: current.grammar_patterns.map((value, itemIndex) => itemIndex === index ? pattern : value),
                      sentences: current.sentences.map(sentence => sentence.pattern_formula === previous.pattern_formula
                        ? { ...sentence, pattern_formula: pattern.pattern_formula } : sentence),
                    }))
                  }} />}
                  {group === 'sentences' && <SentenceFields sentence={item as StagedSentence}
                    patterns={staging.grammar_patterns.filter((_, patternIndex) => !excluded.has(rowKey('grammar_patterns', patternIndex)))}
                    change={sentence => update('sentences', index, sentence)} />}
                </tr>)}
              </tbody>
            </table>
          </div>}
      </section>)}

      <ErrorNotice message={error} />
      <div className="actions stage-actions">
        <Button variant="primary" disabled={saving || selectedCount === 0} onClick={() => void save()}><Save size={18} />{saving ? 'Đang lưu…' : 'Lưu vào kho ôn'}</Button>
        <Button variant="quiet" disabled={saving} onClick={() => { setStaging(null); setError('') }}>Hủy bản xem trước</Button>
        <span className="muted">Đã chọn {selectedCount} mục</span>
      </div>
    </Panel>}

    <Panel title="Thư viện nguồn">
      {sources.loading && <Loading />}
      <ErrorNotice message={sources.error} retry={sources.reload} />
      {sources.data?.length === 0 && <Empty>Tài liệu đã lưu sẽ xuất hiện ở đây.</Empty>}
      {sources.data?.map(source => <article className="source-row" key={source.id}>
        <span className="feature-icon"><FileText size={20} /></span>
        <div className="min-w-0">
          <h3>{source.title}</h3>
          <p className="muted">{sourceLabels[source.source_type]} · {dateLabel(source.created_at)} · {source.word_count} từ · {source.pattern_count} mẫu · {source.sentence_count} câu</p>
          {source.summary_note && <p>{source.summary_note}</p>}
        </div>
        <Link to={withQuery('/hoc', { source_id: source.id, size: 10 })} className="button button-secondary">Ôn theo nguồn</Link>
      </article>)}
    </Panel>
  </div>
}

function LevelInput({ value, onChange }: { value: number | null; onChange: (value: number | null) => void }) {
  return <select aria-label="Cấp độ HSK" value={value ?? ''} onChange={event => onChange(event.target.value ? Number(event.target.value) : null)}>
    <option value="">Mở rộng</option>
    {[1, 2, 3, 4, 5].map(level => <option value={level} key={level}>HSK {level}</option>)}
  </select>
}

function WordFields({ word, change }: { word: StagedWord; change: (word: StagedWord) => void }) {
  return <>
    <td>
      <input aria-label="Từ giản thể" lang="zh-Hans" value={word.simplified} onChange={event => change({ ...word, simplified: event.target.value })} />
      <input aria-label="Pinyin" placeholder="Pinyin" value={word.pinyin} onChange={event => change({ ...word, pinyin: event.target.value })} />
    </td>
    <td><textarea aria-label="Nghĩa tiếng Việt" rows={2} value={word.meaning_vi} onChange={event => change({ ...word, meaning_vi: event.target.value })} /></td>
    <td>
      <LevelBadge level={word.hsk_level} />
      {word.existing && <span className="existing-label">Đã có trong kho (chỉ gắn thêm nguồn)</span>}
      <details>
        <summary>Chỉnh chi tiết</summary>
        <div className="stage-fields">
          <label>Âm Hán Việt<input value={word.han_viet} onChange={event => change({ ...word, han_viet: event.target.value })} /></label>
          <label>Chữ phồn thể<input lang="zh-Hant" value={word.traditional ?? ''} onChange={event => change({ ...word, traditional: event.target.value || null })} /></label>
          <label>Từ loại<input value={word.pos} onChange={event => change({ ...word, pos: event.target.value })} /></label>
          <label>Mẹo nhớ<textarea value={word.mnemonic_vi} onChange={event => change({ ...word, mnemonic_vi: event.target.value })} /></label>
          <label>Cách dùng<textarea value={word.usage_note_vi} onChange={event => change({ ...word, usage_note_vi: event.target.value })} /></label>
          {word.characters.map((character, index) => {
            const modify = (patch: Partial<typeof character>) => change({
              ...word,
              characters: word.characters.map((value, itemIndex) => index === itemIndex ? { ...value, ...patch } : value),
            })
            return <fieldset key={index}>
              <legend lang="zh-Hans">{character.char}</legend>
              <label>Bộ thủ<input value={character.radical} onChange={event => modify({ radical: event.target.value })} /></label>
              <label>Chiết tự<input defaultValue={character.components.join(', ')}
                onBlur={event => modify({ components: event.target.value.split(',').map(value => value.trim()).filter(Boolean) })} /></label>
              <label>Âm Hán Việt<input value={character.han_viet} onChange={event => modify({ han_viet: event.target.value })} /></label>
              <label>Pinyin<input value={character.pinyin} onChange={event => modify({ pinyin: event.target.value })} /></label>
              <label>Mẹo nhớ<textarea value={character.mnemonic_vi} onChange={event => modify({ mnemonic_vi: event.target.value })} /></label>
            </fieldset>
          })}
        </div>
      </details>
    </td>
  </>
}

function PatternFields({ pattern, change }: { pattern: StagedPattern; change: (pattern: StagedPattern) => void }) {
  return <>
    <td><input aria-label="Công thức ngữ pháp" value={pattern.pattern_formula} onChange={event => change({ ...pattern, pattern_formula: event.target.value })} /></td>
    <td><input aria-label="Tên mẫu ngữ pháp" value={pattern.title_vi} onChange={event => change({ ...pattern, title_vi: event.target.value })} />
      <textarea aria-label="Giải thích mẫu ngữ pháp" rows={2} value={pattern.explanation_vi}
        onChange={event => change({ ...pattern, explanation_vi: event.target.value })} /></td>
    <td>
      {pattern.existing && <span className="existing-label">Đã có trong kho</span>}
      <LevelInput value={pattern.hsk_level} onChange={hsk_level => change({ ...pattern, hsk_level })} />
      <textarea aria-label="Ghi chú cấu trúc" placeholder="Ghi chú cấu trúc" rows={2} value={pattern.structure_notes_vi}
        onChange={event => change({ ...pattern, structure_notes_vi: event.target.value })} />
    </td>
  </>
}

function SentenceFields({ sentence, patterns, change }: { sentence: StagedSentence; patterns: StagedPattern[]; change: (sentence: StagedSentence) => void }) {
  const previousMissing = sentence.pattern_formula && !patterns.some(pattern => pattern.pattern_formula === sentence.pattern_formula)
  return <>
    <td>
      <textarea lang="zh-Hans" aria-label="Câu tiếng Trung" rows={2} value={sentence.hanzi} onChange={event => change({ ...sentence, hanzi: event.target.value })} />
      <input aria-label="Pinyin" placeholder="Pinyin" value={sentence.pinyin} onChange={event => change({ ...sentence, pinyin: event.target.value })} />
    </td>
    <td><textarea aria-label="Nghĩa tiếng Việt" rows={2} value={sentence.meaning_vi} onChange={event => change({ ...sentence, meaning_vi: event.target.value })} /></td>
    <td>
      {sentence.existing && <span className="existing-label">Đã có trong kho</span>}
      <select aria-label="Mẫu ngữ pháp liên kết" value={sentence.pattern_formula ?? ''}
        onChange={event => change({ ...sentence, pattern_formula: event.target.value || null })}>
        <option value="">Không chọn mẫu</option>
        {previousMissing && <option value={sentence.pattern_formula ?? ''}>{sentence.pattern_formula}</option>}
        {patterns.map((pattern, index) => <option key={index} value={pattern.pattern_formula}>{pattern.pattern_formula}</option>)}
      </select>
    </td>
  </>
}
