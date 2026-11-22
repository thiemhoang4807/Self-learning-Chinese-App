import { useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'
import type { BackupRestore } from '../types'
import { errorMessage } from '../lib/api'
import { exportBackup, importBackup } from '../lib/backup'
import { useExperience } from './Experience'
import { Modal } from './Modal'
import { Button, ErrorNotice, Panel } from './ui'

function filename(header: string | null) {
  const name = header?.match(/chinese-study-backup-\d{8}-\d{6}\.json/i)?.[0]
  if (name) return name
  const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15).replace('T', '-')
  return 'chinese-study-backup-' + stamp + '.json'
}

export function BackupPanel({ onRestored }: { onRestored: () => void }) {
  const { notify, flushPreferences, applyRestoredPreferences } = useExperience()
  const picker = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [task, setTask] = useState<'export' | 'import' | null>(null)
  const [error, setError] = useState('')
  const [restoreError, setRestoreError] = useState('')
  const [result, setResult] = useState<BackupRestore | null>(null)

  async function download() {
    if (task) return
    setTask('export')
    setError('')
    try {
      await flushPreferences()
      const response = await exportBackup()
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      try {
        link.href = url
        link.download = filename(response.headers.get('Content-Disposition'))
        document.body.appendChild(link)
        link.click()
      } finally {
        link.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 1500)
      }
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setTask(null)
    }
  }

  function choose(selected: File | undefined) {
    if (!selected) return
    setError('')
    if (!selected.name.toLowerCase().endsWith('.json')) {
      setError('Hãy chọn tệp sao lưu có đuôi .json.')
      return
    }
    setRestoreError('')
    setFile(selected)
  }

  async function restore() {
    if (!file || task) return
    setTask('import')
    setRestoreError('')
    try {
      await flushPreferences()
      const restored = await importBackup(file)
      applyRestoredPreferences(restored.preferences)
      setResult(restored)
      setFile(null)
      onRestored()
      notify(restored.message)
    } catch (cause) {
      setRestoreError(errorMessage(cause))
    } finally {
      setTask(null)
    }
  }

  return <Panel title="Sao lưu và khôi phục dữ liệu">
    <p>Lưu từ vựng, nguồn tài liệu, lịch sử ôn, bài viết và cài đặt học vào một tệp JSON.</p>
    <div className="actions">
      <Button variant="primary" disabled={task !== null} onClick={() => void download()}><Download size={18} />
        {task === 'export' ? 'Đang chuẩn bị bản sao lưu…' : 'Tải bản sao lưu (.json)'}
      </Button>
      <input type="file" className="sr-only" aria-hidden="true" tabIndex={-1} ref={picker} accept=".json,application/json" onChange={event => {
        choose(event.target.files?.[0])
        event.target.value = ''
      }} />
      <Button disabled={task !== null} onClick={() => picker.current?.click()}><Upload size={18} />Khôi phục từ tệp sao lưu</Button>
    </div>
    <ErrorNotice message={error} />
    {result && <section className="restore-summary" aria-label="Kết quả khôi phục">
      <h3>Kết quả khôi phục</h3>
      <dl>
        <div><dt>Từ vựng</dt><dd>{result.words_created} thêm, {result.words_updated} cập nhật</dd></div>
        <div><dt>Nguồn tài liệu</dt><dd>{result.sources_created} thêm, {result.sources_updated} cập nhật</dd></div>
        <div><dt>Thẻ ôn</dt><dd>{result.cards_created} thêm, {result.cards_updated} cập nhật</dd></div>
        <div><dt>Lượt ôn</dt><dd>{result.reviews_added} thêm</dd></div>
        <div><dt>Bài viết</dt><dd>{result.stories_added} thêm</dd></div>
      </dl>
    </section>}
    {file && <Modal title="Khôi phục dữ liệu học" busy={task === 'import'} onClose={() => setFile(null)}>
      <p>Tệp đã chọn <strong>{file.name}</strong></p>
      <p>Dữ liệu trong tệp sẽ được gộp vào kho. Tiến độ ôn mới hơn được ưu tiên khi có dữ liệu trùng.</p>
      <ErrorNotice message={restoreError} />
      <div className="actions">
        <Button variant="primary" disabled={task !== null} onClick={() => void restore()}>{task === 'import' ? 'Đang khôi phục…' : 'Xác nhận khôi phục'}</Button>
        <Button variant="quiet" disabled={task !== null} onClick={() => setFile(null)}>Hủy</Button>
      </div>
    </Modal>}
  </Panel>
}
