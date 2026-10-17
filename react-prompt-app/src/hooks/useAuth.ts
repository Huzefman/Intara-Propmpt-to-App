import { useEffect, useState } from 'react'
import { supabase } from '../supabase'

export function useAuth(enabled = true) {
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(enabled)
  useEffect(() => {
    if (!enabled) return
    supabase.auth.getSession().then(({ data }) => { setUser(data.session?.user ?? null); setLoading(false) })
    const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => setUser(session?.user ?? null))
    return () => sub.subscription.unsubscribe()
  }, [enabled])
  return { user, loading, signOut: () => supabase.auth.signOut() }
}
