import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Check, ChevronLeft, ChevronRight, CircleAlert, LoaderCircle, Volume2 } from 'lucide-react'
import { useAudio } from '../hooks/useAudio'
import type { CardStatus } from '../types'

export const statusLabels: Record<CardStatus, string> = {
  new: 'Mới vào hàng đợi',
  learning: 'Đang học',
  review: 'Đang ôn',
  mastered: 'Đã thuộc',
  ignored: 'Tạm bỏ qua',
}

export function Button({ variant = 'secondary', className = '', type = 'button', ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  return <button type={type} className={'button button-' + variant + ' ' + className} {...props} />
}

export function PageTitle({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <header className="page-title">
    <div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {children}
  </header>
}

export function Panel({ children, className = '', title }: { children: ReactNode; className?: string; title?: string }) {
  return <section className={'panel ' + className}>
    {title && <h2>{title}</h2>}
    {children}
  </section>
}

export function Loading({ label = 'Đang tải…' }: { label?: string }) {
  return <div className="loading" role="status"><LoaderCircle size={20} className="animate-spin" />{label}</div>
}

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  if (!message) return null
  return <div className="notice notice-error" role="alert">
    <CircleAlert size={19} /><span>{message}</span>
    {retry && <Button variant="quiet" onClick={retry}>Thử lại</Button>}
  </div>
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="notice" role="status"><Check size={18} />{children}</div>
}

export function StatusBadge({ status }: { status: CardStatus | null }) {
  return <span className={'status status-' + (status ?? 'unknown')}>{status ? statusLabels[status] : 'Chưa ôn'}</span>
}

export function LevelBadge({ level }: { level: number | null }) {
  return <span className="status status-level">{level ? 'HSK ' + level : 'Mở rộng'}</span>
}

export function Speaker({ text, label = 'Nghe phát âm' }: { text: string; label?: string }) {
  const audio = useAudio()
  if (!text.trim()) return null
  return <div className="speaker">
    <Button
      className="icon-button"
      variant="quiet"
      title={label}
      aria-label={label}
      onClick={() => audio.playing ? audio.stop() : audio.play(text)}
    ><Volume2 size={19} /></Button>
    {audio.error && <span role="status" className="small muted">{audio.error}</span>}
  </div>
}

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (value: number) => void }) {
  if (total <= limit) return null
  return <nav className="pager" aria-label="Phân trang">
    <Button className="icon-button" aria-label="Trang trước" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
      <ChevronLeft size={18} />
    </Button>
    <span>Trang {Math.floor(offset / limit) + 1} / {Math.ceil(total / limit)}</span>
    <Button className="icon-button" aria-label="Trang sau" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
      <ChevronRight size={18} />
    </Button>
  </nav>
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}
