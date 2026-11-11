import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { FileManagement } from './page'
import './style.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FileManagement />
  </StrictMode>,
)
