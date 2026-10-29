import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Home } from './pages/Home'
import { TickerPage } from './pages/Ticker'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/ticker/:symbol" element={<TickerPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
