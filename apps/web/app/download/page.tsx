import Link from 'next/link';
export default function DownloadPage() {
  const stores = [ ['App Store',process.env.NEXT_PUBLIC_IOS_APP_STORE_URL], ['Google Play',process.env.NEXT_PUBLIC_PLAY_STORE_URL] ];
  return <main className="mx-auto max-w-xl p-8 text-white"><h1 className="text-3xl">Aventi for iOS and Android</h1><p className="my-5">Discover and save local events in the Aventi mobile app.</p>{stores.map(([name,url]) => url?.startsWith('https://') ? <p key={name} className="my-4"><a href={url} rel="noopener noreferrer">Download on {name}</a></p> : <p key={name}>{name} release is not available yet.</p>)}<nav className="mt-8 flex gap-4"><Link href="/">Home</Link><Link href="/support">Support</Link><Link href="/privacy">Privacy</Link><Link href="/terms">Terms</Link></nav></main>;
}
