import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Plus, X } from 'lucide-react'
import { errorMessage, queueItems } from '../lib/api'
import { useResource } from '../hooks/useResource'
import type { Character, Word } from '../types'
import { Button, Empty, ErrorNotice, Loading, Speaker, StatusBadge } from './ui'

interface Preferences {
  theme: 'light' | 'dark'
  pinyin: boolean
}

interface Experience {
  preferences: Preferences
  toggleTheme: () => void
  togglePinyin: () => void
  showCharacter: (value: string) => void
  notify: (message: string) => void
}

const ExperienceContext = createContext<Experience | null>(null)
const preferenceKey = 'mandarin-study.preferences'

function initialPreferences(): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(preferenceKey) || '{}')
    return {
      theme: saved.theme === 'dark' ? 'dark' : 'light',
      pinyin: saved.pinyin === true,
    }
  } catch {
    return { theme: 'light', pinyin: false }
  }
}

export function ExperienceProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(initialPreferences)
  const [character, setCharacter] = useState('')
  const [notice, setNotice] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    document.documentElement.dataset.theme = preferences.theme
    try { localStorage.setItem(preferenceKey, JSON.stringify(preferences)) } catch { /* Storage may be disabled. */ }
  }, [preferences])

  useEffect(() => () => clearTimeout(timer.current), [])
  const notify = useCallback((message: string) => {
    clearTimeout(timer.current)
    setNotice(message)
    timer.current = setTimeout(() => setNotice(''), 3800)
  }, [])

  return <ExperienceContext.Provider value={{
    preferences,
    toggleTheme: () => setPreferences(current => ({ ...current, theme: current.theme === 'light' ? 'dark' : 'light' })),
    togglePinyin: () => setPreferences(current => ({ ...current, pinyin: !current.pinyin })),
    showCharacter: setCharacter,
    notify,
  }}>
    {children}
    {character && <CharacterDrawer character={character} close={() => setCharacter('')} />}
    {notice && <div className="toast" role="status">{notice}</div>}
  </ExperienceContext.Provider>
}

export function useExperience() {
  const context = useContext(ExperienceContext)
  if (!context) throw new Error('ExperienceProvider is missing')
  return context
}

export function Hanzi({ text, className = '', linked = true, mixed = false }: { text: string; className?: string; linked?: boolean; mixed?: boolean }) {
  const { showCharacter } = useExperience()
  return <span className={'hanzi ' + (mixed ? 'hanzi-mixed ' : '') + className} lang={mixed ? undefined : 'zh-Hans'}>
    {linked ? Array.from(text).map((character, index) => /\p{Script=Han}/u.test(character)
      ? <button type="button" key={index} className="hanzi-char" lang="zh-Hans" title={'Xem chiết tự chữ ' + character}
        aria-label={'Xem chiết tự chữ ' + character} onClick={() => showCharacter(character)}>{character}</button>
      : character) : text}
  </span>
}

export function Pinyin({ text, visible }: { text: string; visible?: boolean }) {
  const { preferences } = useExperience()
  return text && (visible ?? preferences.pinyin) ? <span className="pinyin">{text}</span> : null
}

export function CharacterDetails({ character, pinyinVisible = true }: { character: Character; pinyinVisible?: boolean }) {
  return <>
    <div className="definition-meta">
      <Pinyin text={character.pinyin} visible={pinyinVisible} />
      {character.han_viet && <span className="han-viet">{character.han_viet}</span>}
    </div>
    {character.radical && <div className="detail-line"><strong>Bộ thủ</strong><Hanzi text={character.radical} /></div>}
    {character.components_json.length > 0 && <div className="detail-line">
      <strong>Chiết tự</strong><Hanzi text={character.components_json.join(' ＋ ')} />
    </div>}
    {character.mnemonic_vi && <p className="mnemonic">{character.mnemonic_vi}</p>}
  </>
}

function CharacterDrawer({ character, close }: { character: string; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const resource = useResource<{ character: Character; words: Word[] }>('/vault/characters/' + encodeURIComponent(character))
  const { notify } = useExperience()
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [queued, setQueued] = useState<number[]>([])

  useEffect(() => {
    const element = dialog.current
    if (element && !element.open) element.showModal()
    return () => element?.close()
  }, [])

  async function add(word: Word) {
    setBusy(word.id)
    setError('')
    try {
      await queueItems('word', [word.id])
      setQueued(current => [...current, word.id])
      notify('Đã thêm “' + word.simplified + '” vào hàng đợi ôn.')
    } catch (cause) {
      setError(errorMessage(cause))
    } finally {
      setBusy(null)
    }
  }

  const groups = [1, 2, 3, 4, 5, null].map(level => ({
    level,
    words: resource.data?.words.filter(word => word.hsk_level === level) ?? [],
  })).filter(group => group.words.length > 0)

  return <dialog className="character-drawer" ref={dialog} aria-labelledby="drawer-title"
    onCancel={event => { event.preventDefault(); close() }}
    onClick={event => { if (event.target === event.currentTarget) close() }}>
    <div className="drawer-content">
      <div className="split">
        <h2 id="drawer-title">Cây liên kết chữ gốc</h2>
        <Button className="icon-button" variant="quiet" aria-label="Đóng cây chữ" autoFocus onClick={close}><X size={22} /></Button>
      </div>

      <div className="drawer-glyph">
        <Hanzi text={character} linked={false} />
        <Speaker text={character} />
      </div>
      {resource.loading && <Loading />}
      <ErrorNotice message={resource.error} retry={resource.reload} />
      <ErrorNotice message={error} />

      {resource.data && <>
        <CharacterDetails character={resource.data.character} />
        <div className="tree-groups">
          <h3>Từ có chữ này</h3>
          {!groups.length && <Empty>Chưa có từ chứa chữ này trong kho.</Empty>}
          {groups.map(group => <section className="tree-group" key={group.level ?? 'extended'}>
            <h4>{group.level ? 'HSK ' + group.level : 'Mở rộng'}</h4>
            {group.words.map(word => {
              const status = queued.includes(word.id) ? 'new' : word.status
              return <div key={word.id} className="tree-word">
                <div><Hanzi text={word.simplified} /><Pinyin text={word.pinyin} /><span>{word.meaning_vi}</span></div>
                {status && status !== 'ignored' ? <StatusBadge status={status} /> : <Button aria-label={'Thêm ' + word.simplified + ' vào hàng đợi ôn'} disabled={busy !== null} onClick={() => void add(word)}><Plus size={17} />Thêm ôn</Button>}
              </div>
            })}
          </section>)}
        </div>
      </>}
    </div>
  </dialog>
}

const partOfSpeech: Record<string, string> = {
  noun: 'Danh từ', verb: 'Động từ', adjective: 'Tính từ', adverb: 'Phó từ',
  pronoun: 'Đại từ', numeral: 'Số từ', 'measure word': 'Lượng từ', interjection: 'Thán từ',
  conjunction: 'Liên từ', preposition: 'Giới từ', particle: 'Trợ từ', 'proper noun': 'Danh từ riêng',
  'modal verb': 'Động từ tình thái', phrase: 'Cụm từ', 'auxiliary verb': 'Trợ động từ',
  'directional verb': 'Động từ chỉ hướng', idiom: 'Thành ngữ', determiner: 'Từ hạn định', classifier: 'Lượng từ',
}

export function vietnamesePartOfSpeech(value: string) {
  return value.split('/').map(entry => {
    const part = entry.trim()
    return partOfSpeech[part.toLowerCase()] || (/[À-ỹ]/u.test(part) ? part : '')
  }).filter(Boolean).join(' / ')
}

export function WordDefinition({ word }: { word: Word }) {
  return <>
    <div className="split word-heading">
      <Hanzi text={word.simplified} />
      <Speaker text={word.simplified} />
    </div>
    <div className="definition-meta">
      <Pinyin text={word.pinyin} visible />
      {word.han_viet && <span className="han-viet">{word.han_viet}</span>}
      {vietnamesePartOfSpeech(word.pos) && <span className="muted">{vietnamesePartOfSpeech(word.pos)}</span>}
    </div>
    {word.meaning_vi && <p>{word.meaning_vi}</p>}
    {word.mnemonic_vi && <p className="mnemonic">{word.mnemonic_vi}</p>}
    {word.usage_note_vi && <p className="muted">{word.usage_note_vi}</p>}
  </>
}
