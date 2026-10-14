import { Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { OverviewPage } from './pages/OverviewPage'
import { ResourcesPage } from './pages/ResourcesPage'
import { MonitoringPage } from './pages/MonitoringPage'
import { InvestigatePage } from './pages/InvestigatePage'
import { InvestigationDetailPage } from './pages/InvestigationDetailPage'
import { HistoryPage } from './pages/HistoryPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/resources" element={<ResourcesPage />} />
        <Route path="/monitoring" element={<MonitoringPage />} />
        <Route path="/investigate" element={<InvestigatePage />} />
        <Route path="/investigations/:id" element={<InvestigationDetailPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
    </Routes>
  )
}
