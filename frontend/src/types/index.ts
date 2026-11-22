export type CardStatus = 'new' | 'learning' | 'review' | 'mastered' | 'ignored'
export type ItemType = 'word' | 'pattern' | 'confusable'
export type DrillMode = 'flashcard' | 'listening' | 'cloze' | 'reorder' | 'reverse' | 'confusable'
export type Rating = 1 | 2 | 3 | 4
export type SourceType = 'image' | 'pdf' | 'pptx' | 'docx' | 'xlsx' | 'text' | 'paste'

export interface Character {
  char: string
  pinyin: string
  han_viet: string
  radical: string
  components_json: string[]
  mnemonic_vi: string
  hsk_level?: number | null
}

export interface Word {
  id: number
  simplified: string
  traditional: string | null
  pinyin: string
  han_viet: string
  meaning_vi: string
  pos: string
  hsk_level: number | null
  mnemonic_vi: string
  usage_note_vi: string
  status: CardStatus | null
}

export interface Sentence {
  id: number
  hanzi: string
  pinyin: string
  meaning_vi: string
  grammar_pattern_id?: number | null
  is_ai_generated?: boolean
}

export interface Pattern {
  id: number
  pattern_formula: string
  title_vi: string
  explanation_vi: string
  hsk_level: number | null
  structure_notes_vi: string
}

export interface Card {
  id: number
  item_id: number
  item_type: ItemType
  status: CardStatus
  mode: DrillMode
  hanzi: string
  pinyin: string
  han_viet: string
  meaning_vi: string
  mnemonic_vi: string
  usage_note_vi: string
  grammar_hint: string
  audio_text: string
  characters: Character[]
  sentences: Sentence[]
  sentence_id: number | null
  prompt: string
  answer: string
  choices: string[]
  tiles: string[]
}

export interface Source {
  id: number
  title: string
  source_type: SourceType
  summary_note: string
  created_at: string
  word_count: number
  pattern_count: number
  sentence_count: number
}

export interface StagedWord extends Omit<Word, 'id' | 'status'> {
  characters: Array<Omit<Character, 'components_json'> & { components: string[] }>
  existing: boolean
}

export interface StagedPattern {
  pattern_formula: string
  title_vi: string
  explanation_vi: string
  hsk_level: number | null
  structure_notes_vi: string
  existing: boolean
}

export interface StagedSentence {
  hanzi: string
  pinyin: string
  meaning_vi: string
  pattern_formula: string | null
  existing: boolean
}

export interface Staging {
  title: string
  source_type: SourceType
  summary_note: string
  notice_vi?: string | null
  words: StagedWord[]
  grammar_patterns: StagedPattern[]
  sentences: StagedSentence[]
}

export interface HskLevel {
  level: number
  mastered: number
  ingested: number
  total: number
  available: number
}

export interface Pace {
  words_per_day: number
  remaining: number
  projected_date: string | null
}

export interface Dashboard {
  levels: HskLevel[]
  pace: Pace
  leeches: {
    card_id: number
    word_id: number
    simplified: string
    pinyin: string
    meaning_vi: string
    wrong_count: number
  }[]
}

export interface Pair {
  id: number
  word_a_id: number
  word_b_id: number
  word_a: string
  word_b: string
  diff_explanation_vi: string
  cloze_a_hanzi: string
  cloze_a_answer: string
  cloze_b_hanzi: string
  cloze_b_answer: string
  hsk_level: number | null
}

export interface ReverseFeedback {
  score: number
  feedback_vi: string
  corrections: { original: string; correction: string; explanation_vi: string }[]
  corrected_hanzi: string
}

export interface StoryAttempt {
  id: number
  target_words: string[]
  text: string
  score: number
  created_at: string
  feedback: {
    usage: { word: string; correct: boolean; feedback_vi: string }[]
    grammar_vi: string
    naturalness_vi: string
    rewrite_hanzi: string
  }
}

export interface ReaderToken { text: string; word: Word | null }
export interface PageResult<T> { items: T[]; total: number }
export interface Settings { gemini_configured: boolean; gemini_model: string }

export interface Preferences {
  theme: 'light' | 'dark'
  pinyin: boolean
}

export interface Health extends Settings {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
  hsk_word_count: number | null
  tts_cache_count: number | null
}

export interface BackupRestore {
  words_created: number
  words_updated: number
  sources_created: number
  sources_updated: number
  cards_created: number
  cards_updated: number
  reviews_added: number
  stories_added: number
  preferences: Preferences
  message: string
}
