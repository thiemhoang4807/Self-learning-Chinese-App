import { useEffect } from 'react'
import { BookOpenText, ChartNoAxesColumn, CloudUpload, House, Moon, Sun, TreePine } from 'lucide-react'
import { Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { ExperienceProvider, useExperience } from './components/Experience'
import { Button } from './components/ui'
import { Home } from './pages/Home'
import { Study } from './pages/Study'
import { Passive } from './pages/Passive'
import { Ingest } from './pages/Ingest'
import { Tools } from './pages/Tools'
import { Vault } from './pages/Vault'
import { Progress } from './pages/Progress'

const navigation = [
  { route: '/', label: 'Học hôm nay', short: 'Hôm nay', icon: House },
  { route: '/tai-lieu', label: 'Nạp tài liệu', short: 'Tài liệu', icon: CloudUpload },
  { route: '/luyen-hsk', label: 'Luyện HSK 4–5', short: 'Luyện HSK', icon: BookOpenText },
  { route: '/tu-dien', label: 'Từ điển và Cây chữ', short: 'Từ điển', icon: TreePine },
  { route: '/tien-do', label: 'Tiến độ HSK', short: 'Tiến độ', icon: ChartNoAxesColumn },
]

function Layout() {
  const { preferences, toggleTheme } = useExperience()
  const { pathname } = useLocation()
  const study = pathname === '/hoc' || pathname === '/nghe'
  const themeLabel = preferences.theme === 'dark' ? 'Dùng giao diện sáng' : 'Dùng giao diện tối'

  useEffect(() => { window.scrollTo(0, 0) }, [pathname])

  return <div className="app-layout">
    <a className="skip-link" href="#main">Đến nội dung</a>
    <aside className="sidebar">
      <Link className="brand" to="/">
        <span className="brand-symbol" lang="zh-Hans" aria-hidden="true">学</span>
        <span>Học Trung</span>
      </Link>
      <nav className="desktop-nav" aria-label="Điều hướng chính">
        {navigation.map(({ route, label, icon: Icon }) => <NavLink className={({ isActive }) => isActive || (study && route === '/') ? 'nav-link active' : 'nav-link'}
          key={route} to={route} end={route === '/'}>
          <Icon size={20} aria-hidden="true" /><span>{label}</span>
        </NavLink>)}
      </nav>
      <Button className="theme-button" variant="quiet" onClick={toggleTheme}>
        {preferences.theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}{themeLabel}
      </Button>
    </aside>
    <div className="mobile-header">
      <Link className="brand" to="/"><span className="brand-symbol" lang="zh-Hans" aria-hidden="true">学</span>Học Trung</Link>
      <Button className="icon-button" variant="quiet" aria-label={themeLabel} title={themeLabel} onClick={toggleTheme}>
        {preferences.theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
      </Button>
    </div>
    <main className={'main-content' + (study ? ' main-study' : '')} id="main">
      <Outlet />
    </main>
    <nav className="mobile-nav" aria-label="Điều hướng chính">
      {navigation.map(({ route, short, label, icon: Icon }) => <NavLink className={({ isActive }) => isActive || (study && route === '/') ? 'active' : ''}
        key={route} to={route} aria-label={label} end={route === '/'}>
        <Icon size={21} aria-hidden="true" /><span>{short}</span>
      </NavLink>)}
    </nav>
  </div>
}

export default function App() {
  return <ExperienceProvider>
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="hoc" element={<Study />} />
        <Route path="nghe" element={<Passive />} />
        <Route path="tai-lieu" element={<Ingest />} />
        <Route path="luyen-hsk/*" element={<Tools />} />
        <Route path="tu-dien" element={<Vault />} />
        <Route path="tien-do" element={<Progress />} />
        <Route path="*" element={<div className="panel"><h1>Không tìm thấy trang</h1><Link className="text-link" to="/">Về trang Học hôm nay</Link></div>} />
      </Route>
    </Routes>
  </ExperienceProvider>
}
