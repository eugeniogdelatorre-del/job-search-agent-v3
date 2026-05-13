'use client'

// CV uploader — dashed-border dark drag-drop zone.
// Drag-over state: border → cyan, subtle bg tint.

import { useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'

export function ResumeUploader() {
  const router     = useRouter()
  const [dragging,  setDragging]  = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef   = useRef<HTMLInputElement>(null)
  // Audit N-H8: AbortController so unmounting cancels the upload. The
  // mountedRef guards against `setState on unmounted component` warnings
  // for both the early-return paths and the post-fetch finally.
  const abortRef   = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  async function upload(file: File) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('PDF only')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('File must be under 5MB')
      return
    }
    // Abort any in-flight upload before starting a new one — e.g. user
    // drops a second file while the first is still parsing.
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/cv/upload', {
        method: 'POST',
        body: form,
        signal: controller.signal,
      })
      const json = await res.json()
      if (!mountedRef.current) return
      if (!res.ok) { toast.error(json.error || 'Upload failed'); return }
      if (json.duplicate)  toast.success('Already uploaded — using the existing version')
      else if (json.is_active) toast.success('CV uploaded and activated')
      else toast.success('CV uploaded — click activate to use it')
      router.refresh()
    } catch (e) {
      if (controller.signal.aborted) return  // unmount or replaced — silent
      if (!mountedRef.current) return
      toast.error(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      if (mountedRef.current) setUploading(false)
      if (abortRef.current === controller) abortRef.current = null
    }
  }

  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-xl p-10 text-center transition-colors"
      style={{
        border:      `2px dashed ${dragging ? '#00D4FF' : '#252D40'}`,
        background:  dragging ? 'rgba(0,212,255,0.04)' : 'transparent',
        opacity:     uploading ? 0.6 : 1,
        pointerEvents: uploading ? 'none' : 'auto',
        cursor:      'pointer',
        transition:  'border-color 0.15s, background 0.15s',
      }}
      onDragOver={(e)  => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const f = e.dataTransfer.files?.[0]
        if (f) upload(f)
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) upload(f)
          e.target.value = ''
        }}
      />
      {uploading ? (
        <Loader2 className="h-6 w-6 animate-spin" style={{ color: '#6B7A99' }} />
      ) : (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={dragging ? '#00D4FF' : '#6B7A99'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
          <polyline points="17 8 12 3 7 8"/>
          <line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      )}
      <p className="font-mono text-[12px] font-medium" style={{ color: uploading ? '#6B7A99' : '#E8ECF0' }}>
        {uploading ? 'Parsing PDF…' : 'Drop a PDF here, or click to browse'}
      </p>
      <p className="font-mono text-[10px]" style={{ color: '#3A4460' }}>
        Text PDF · max 5 MB · only parsed text is stored
      </p>
    </div>
  )
}
