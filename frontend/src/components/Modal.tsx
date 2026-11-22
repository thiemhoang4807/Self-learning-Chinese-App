import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import { Button } from './ui'

export function Modal({ title, children, onClose, busy = false }: {
  title: string
  children: ReactNode
  onClose: () => void
  busy?: boolean
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  return <dialog ref={dialog} className="edit-modal" aria-labelledby={titleId}
    onCancel={event => { event.preventDefault(); if (!busy) onClose() }}
    onClick={event => { if (!busy && event.currentTarget === event.target) onClose() }}>
    <div className="modal-content">
      <div className="split">
        <h2 id={titleId}>{title}</h2>
        <Button className="icon-button" variant="quiet" aria-label="Đóng" onClick={onClose} disabled={busy}><X size={21} /></Button>
      </div>
      {children}
    </div>
  </dialog>
}
