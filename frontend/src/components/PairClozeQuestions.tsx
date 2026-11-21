import { useState } from 'react'
import { Hanzi } from './Experience'
import { Button } from './ui'

export function PairClozeQuestions({ prompts, choices, correct, onSubmit }: {
  prompts: [string, string]
  choices: string[]
  correct: [string, string]
  onSubmit?: (answers: [string, string]) => void
}) {
  const [answers, setAnswers] = useState<[string, string]>(['', ''])
  const [checked, setChecked] = useState(false)
  const score = answers.filter((answer, index) => answer === correct[index]).length

  return <>
    <div className="pair-clozes">
      {prompts.map((prompt, index) => <div className="cloze-panel" key={index}>
        <h3><Hanzi text={prompt} /></h3>
        <div className="choices">
          {choices.map(word => <Button key={word} aria-pressed={answers[index] === word} disabled={checked}
            onClick={() => setAnswers(current => index === 0 ? [word, current[1]] : [current[0], word])}>
            <Hanzi text={word} linked={false} />
          </Button>)}
        </div>
        {checked && <div className="detail-line">
          <strong>{answers[index] === correct[index] ? 'Đúng rồi' : 'Đáp án'}</strong><Hanzi text={correct[index]} />
        </div>}
      </div>)}
    </div>
    <div className="actions">
      {checked
        ? <><span role="status">{score}/2 câu đúng</span><Button onClick={() => { setAnswers(['', '']); setChecked(false) }}>Làm lại</Button></>
        : <Button variant="primary" disabled={answers.some(answer => !answer)} onClick={() => {
          if (onSubmit) onSubmit(answers)
          else setChecked(true)
        }}>Kiểm tra hai câu</Button>}
    </div>
  </>
}
