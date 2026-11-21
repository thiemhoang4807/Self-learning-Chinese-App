import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AudioLines, BookOpenText, Brain, Headphones, Layers3, Shuffle, Target, Zap } from 'lucide-react'
import { useResource } from '../hooks/useResource'
import { withQuery } from '../lib/api'
import type { Dashboard, Pace, Source } from '../types'
import { Empty, ErrorNotice, Loading, Panel } from '../components/ui'

export function PaceNote({ pace }: { pace: Pace }) {
  if (pace.remaining === 0) return <p>Bạn đã phủ hết vốn từ mục tiêu HSK 1–5.</p>
  const velocity = Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 }).format(pace.words_per_day)
  const match = pace.projected_date?.match(/^(\d{4})-(\d{2})/)
  if (!match) return <p>Một vài buổi ôn sẽ giúp bạn thấy nhịp học của mình ở đây.</p>
  return <p>Với nhịp học 7 ngày gần nhất (~{velocity} từ/ngày), dự kiến phủ xong HSK 5 vào tháng {Number(match[2])}/{match[1]}.</p>
}

const drills = [
  { mode: 'flashcard', label: 'Nhận diện mặt chữ', icon: Brain },
  { mode: 'listening', label: 'Nghe chay', icon: AudioLines },
  { mode: 'cloze', label: 'Điền từ', icon: Layers3 },
  { mode: 'reorder', label: 'Xếp từ thành câu', icon: Shuffle },
  { mode: 'reverse', label: 'Dịch Việt sang Trung', icon: BookOpenText },
] as const

export function Home() {
  const dashboard = useResource<Dashboard>('/dashboard')
  const sources = useResource<Source[]>('/ingestion/sources')
  const [source, setSource] = useState('')
  const [level, setLevel] = useState('')
  const [size, setSize] = useState(10)

  return <div className="page-stack">
    <section className="hero">
      <div className="hero-copy">
        <h1>Học hôm nay</h1>
        <p>Một lượt ôn vừa sức để nhớ thêm vài từ tiếng Trung.</p>
        <Link className="button button-hero" to="/hoc?size=8"><Zap size={20} />Học nhanh 2 phút</Link>
      </div>
      <span className="hero-character" lang="zh-Hans" aria-hidden="true">学</span>
    </section>

    <div className="home-grid">
      <Panel title="Luyện theo cách bạn thích">
        <div className="drill-links">
          {drills.map(({ mode, label, icon: Icon }) => <Link key={mode} to={withQuery('/hoc', { size: 10, mode })} className="drill-link">
            <span className="feature-icon"><Icon size={20} /></span><span>{label}</span>
          </Link>)}
        </div>
      </Panel>
      <div className="page-stack">
        <Panel className="passive-promo">
          <span className="feature-icon feature-icon-blue"><Headphones size={21} /></span>
          <h2>Chế độ Học Lười</h2>
          <p>Nghe, nhẩm nghĩa, rồi để ứng dụng tự chuyển thẻ.</p>
          <Link className="button button-secondary" to="/nghe?size=10">Bắt đầu nghe</Link>
        </Panel>
        <Panel>
          <div className="section-heading"><Target size={21} /><h2>Nhịp học HSK</h2></div>
          {dashboard.loading && <Loading />}
          <ErrorNotice message={dashboard.error} retry={dashboard.reload} />
          {dashboard.data && <PaceNote pace={dashboard.data.pace} />}
          <Link className="text-link" to="/tien-do">Xem tiến độ</Link>
        </Panel>
      </div>
    </div>

    <Panel title="Chọn một buổi ôn">
      <div className="form-grid session-options">
        <label>Nguồn tài liệu
          <select value={source} onChange={event => setSource(event.target.value)}>
            <option value="">Mọi nguồn</option>
            {sources.data?.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
          </select>
        </label>
        <label>Cấp độ
          <select value={level} onChange={event => setLevel(event.target.value)}>
            <option value="">Mọi cấp độ</option>
            {[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>HSK {value}</option>)}
          </select>
        </label>
        <label>Số thẻ
          <select value={size} onChange={event => setSize(Number(event.target.value))}>
            {[10, 20, 30].map(value => <option key={value} value={value}>{value} thẻ</option>)}
          </select>
        </label>
        <Link className="button button-primary" to={withQuery('/hoc', { source_id: source, hsk_level: level, size })}>Bắt đầu ôn</Link>
      </div>
      <ErrorNotice message={sources.error} retry={sources.reload} />
      {sources.data?.length === 0 && <Empty>Bạn có thể nạp tài liệu để tạo buổi ôn theo nguồn.</Empty>}
    </Panel>
  </div>
}
