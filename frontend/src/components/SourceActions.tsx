import { useState } from 'react'
import { PencilLine, Trash2 } from 'lucide-react'
import type { Source } from '../types'
import { errorMessage } from '../lib/api'
import { deleteSource, updateSource } from '../lib/library'
import { useExperience } from './Experience'
import { Modal } from './Modal'
import { Button, ErrorNotice } from './ui'

export function SourceActions({ source, onUpdated, onDeleted }: {
  source: Source
  onUpdated: (source: Source) => void
  onDeleted: (id: number) => void
}) {
  const { notify } = useExperience()
  const [action, setAction] = useState<'rename' | 'delete' | null>(null)
  const [title, setTitle] = useState(source.title)
  const [summaryNote, setSummaryNote] = useState(source.summary_note)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function open(next: 'rename' | 'delete') {
    setTitle(source.title)
    setSummaryNote(source.summary_note)
    setError('')
    setAction(next)
  }

  async function save() {
    if (busy || !title.trim()) return
    setBusy(true)
    setError('')
    try {
      if (action === 'delete') {
        await deleteSource(source.id)
        onDeleted(source.id)
        notify('Đã xóa nguồn “' + source.title + '”.')
      } else {
        const updated = await updateSource(source.id, { title: title.trim(), summary_note: summaryNote.trim() })
        onUpdated(updated)
        notify('Đã cập nhật nguồn tài liệu.')
      }
      setAction(null)
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <Button variant="quiet" onClick={() => open('rename')}><PencilLine size={16} />Đổi tên</Button>
    <Button variant="quiet" onClick={() => open('delete')}><Trash2 size={16} />Xóa nguồn</Button>
    {action && <Modal title={action === 'rename' ? 'Đổi tên nguồn' : 'Xóa nguồn tài liệu'} busy={busy} onClose={() => setAction(null)}>
      <form className="page-stack" onSubmit={event => { event.preventDefault(); void save() }}>
        {action === 'rename' ? <>
          <label>Tên nguồn<input required maxLength={250} value={title} onChange={event => setTitle(event.target.value)} /></label>
          <label>Ghi chú nguồn<textarea rows={3} maxLength={4000} value={summaryNote} onChange={event => setSummaryNote(event.target.value)} /></label>
        </> : <p>Xóa “{source.title}” khỏi thư viện? Từ vựng, mẫu ngữ pháp, câu ví dụ và lịch sử ôn được giữ lại.</p>}
        <ErrorNotice message={error} />
        <div className="actions">
          <Button type="submit" variant={action === 'rename' ? 'primary' : 'danger'} disabled={busy || !title.trim()}>
            {busy ? 'Đang xử lý…' : action === 'rename' ? 'Lưu thay đổi' : 'Xác nhận xóa nguồn'}
          </Button>
          <Button variant="quiet" disabled={busy} onClick={() => setAction(null)}>Hủy</Button>
        </div>
      </form>
    </Modal>}
  </>
}
