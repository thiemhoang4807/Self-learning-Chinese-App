import { useState } from 'react'
import type { FormEvent } from 'react'
import { PencilLine, Save } from 'lucide-react'
import { Modal } from './Modal'
import { Button, ErrorNotice, Loading } from './ui'
import { useExperience } from './Experience'
import { useResource } from '../hooks/useResource'
import { errorMessage } from '../lib/api'
import { knowledgePath, updateKnowledge } from '../lib/library'
import type { LibraryEntities, LibraryEntity } from '../lib/library'

interface Field {
  key: string
  label: string
  type: 'text' | 'paragraph' | 'level'
  max?: number
}

const pinyin: Field = { key: 'pinyin', label: 'Pinyin', type: 'text', max: 200 }
const meaning: Field = { key: 'meaning_vi', label: 'Nghĩa tiếng Việt', type: 'paragraph', max: 4000 }
const level: Field = { key: 'hsk_level', label: 'Cấp độ HSK', type: 'level' }
const fields: Record<LibraryEntity, Field[]> = {
  word: [
    pinyin,
    { key: 'han_viet', label: 'Âm Hán Việt', type: 'text', max: 200 },
    meaning,
    { key: 'pos', label: 'Từ loại', type: 'text', max: 100 },
    level,
    { key: 'mnemonic_vi', label: 'Mẹo nhớ', type: 'paragraph' },
    { key: 'usage_note_vi', label: 'Cách dùng', type: 'paragraph' },
  ],
  pattern: [
    { key: 'title_vi', label: 'Tên mẫu ngữ pháp', type: 'text', max: 250 },
    { key: 'explanation_vi', label: 'Giải thích', type: 'paragraph', max: 4000 },
    level,
    { key: 'structure_notes_vi', label: 'Ghi chú cấu trúc', type: 'paragraph' },
  ],
  sentence: [{ ...pinyin, max: 4000 }, meaning],
}
const kindLabels: Record<LibraryEntity, string> = { word: 'từ vựng', pattern: 'mẫu ngữ pháp', sentence: 'câu ví dụ' }

export function EditKnowledgeButton<K extends LibraryEntity>({ kind, id, onSaved, label }: {
  kind: K
  id: number
  onSaved: (item: LibraryEntities[K]) => void
  label?: string
}) {
  const [open, setOpen] = useState(false)
  return <>
    <Button variant="quiet" onClick={() => setOpen(true)}><PencilLine size={16} />{label ?? 'Sửa ' + kindLabels[kind]}</Button>
    {open && <KnowledgeEditor kind={kind} id={id} onSaved={onSaved} onClose={() => setOpen(false)} />}
  </>
}

function KnowledgeEditor<K extends LibraryEntity>({ kind, id, onSaved, onClose }: {
  kind: K
  id: number
  onSaved: (item: LibraryEntities[K]) => void
  onClose: () => void
}) {
  const { notify } = useExperience()
  const item = useResource<LibraryEntities[K]>(knowledgePath(kind, id))
  const [updates, setUpdates] = useState<Record<string, string | number | null>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || !Object.keys(updates).length) return
    setBusy(true)
    setError('')
    try {
      const saved = await updateKnowledge(kind, id, updates)
      onSaved(saved)
      onClose()
      notify('Đã cập nhật ' + kindLabels[kind] + '.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  const record = item.data as unknown as Record<string, unknown> | null
  const hanzi = String(record?.simplified ?? record?.pattern_formula ?? record?.hanzi ?? '')
  return <Modal title={'Sửa ' + kindLabels[kind]} onClose={onClose} busy={busy}>
    {item.loading && <Loading />}
    <ErrorNotice message={item.error} retry={item.reload} />
    {record && <form className="page-stack" onSubmit={event => void save(event)}>
      <p className="editor-hanzi" lang="zh-Hans">{hanzi}</p>
      {fields[kind].map(field => {
        const value = Object.hasOwn(updates, field.key) ? updates[field.key] : record[field.key]
        const update = (next: string | number | null) => setUpdates(previous => ({ ...previous, [field.key]: next }))
        return <label key={field.key}>{field.label}
          {field.type === 'level' ? <select value={String(value ?? '')}
            onChange={event => update(event.target.value ? Number(event.target.value) : null)}>
            <option value="">Mở rộng</option>
            {[1, 2, 3, 4, 5].map(number => <option key={number} value={number}>HSK {number}</option>)}
          </select> : field.type === 'paragraph'
            ? <textarea rows={3} value={String(value ?? '')} maxLength={field.max} onChange={event => update(event.target.value)} />
            : <input value={String(value ?? '')} maxLength={field.max} onChange={event => update(event.target.value)} />}
        </label>
      })}
      {kind === 'word' && <label>Hàng đợi ôn
        <select value={String(updates.status ?? (record.status === 'ignored' ? 'ignored' : 'active'))}
          onChange={event => setUpdates(previous => ({ ...previous, status: event.target.value }))}>
          <option value="active">Cho phép ôn</option>
          <option value="ignored">Tạm bỏ qua</option>
        </select>
      </label>}
      <ErrorNotice message={error} />
      <div className="actions">
        <Button type="submit" variant="primary" disabled={busy || !Object.keys(updates).length}><Save size={17} />{busy ? 'Đang lưu…' : 'Lưu thay đổi'}</Button>
        <Button variant="quiet" onClick={onClose} disabled={busy}>Hủy</Button>
      </div>
    </form>}
  </Modal>
}
