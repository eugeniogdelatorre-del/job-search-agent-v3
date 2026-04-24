'use client'

// CV uploader — drag-drop or click, PDF only, ≤5MB.
// POSTs to /api/cv/upload, toasts success/error, refreshes the page so
// the server-rendered version list updates.

import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { UploadCloud, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export function ResumeUploader() {
  const router = useRouter()
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  async function upload(file: File) {
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast.error('PDF only')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      toast.error('File must be under 5MB')
      return
    }
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const res = await fetch('/api/cv/upload', { method: 'POST', body: form })
      const json = await res.json()
      if (!res.ok) {
        toast.error(json.error || 'Upload failed')
        return
      }
      if (json.duplicate) {
        toast.success('Already uploaded — using the existing version')
      } else if (json.is_active) {
        toast.success('CV uploaded and activated')
      } else {
        toast.success('CV uploaded — click Activate to use it')
      }
      router.refresh()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center transition-colors',
        dragging ? 'border-primary bg-primary/5' : 'border-muted-foreground/30',
        uploading && 'opacity-60 pointer-events-none'
      )}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
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
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      ) : (
        <UploadCloud className="h-6 w-6 text-muted-foreground" />
      )}
      <p className="text-sm font-medium">
        {uploading ? 'Parsing PDF…' : 'Drop a PDF here, or click to browse'}
      </p>
      <p className="text-xs text-muted-foreground">
        Text PDF, max 5 MB. Only the parsed text is stored.
      </p>
    </div>
  )
}
