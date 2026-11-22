import type { Pattern, Sentence, Source, Word } from '../types'
import { api } from './api'

export interface LibraryEntities {
  word: Word
  pattern: Pattern
  sentence: Sentence
}

export type LibraryEntity = keyof LibraryEntities
type LibraryPath = '/words' | '/patterns' | '/sentences'
const paths: Record<LibraryEntity, LibraryPath> = { word: '/words', pattern: '/patterns', sentence: '/sentences' }

export const knowledgePath = (kind: LibraryEntity, id: number) => paths[kind] + '/' + id

export const updateKnowledge = <K extends LibraryEntity>(kind: K, id: number, body: Record<string, unknown>) =>
  api<LibraryEntities[K]>(knowledgePath(kind, id), { method: 'PATCH', body })

export const updateSource = (id: number, body: { title: string; summary_note: string }) =>
  api<Source>('/sources/' + id, { method: 'PATCH', body })

export const deleteSource = (id: number) => api<void>('/sources/' + id, { method: 'DELETE' })
