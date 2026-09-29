import { Linking, Pressable, Text, View } from 'react-native';
import type { MembershipOffer } from '../lib/revenuecat';

export function MembershipPlans({ offers, enabled, loading, busy, onPurchase, onLoad, onRestore, onManage }: {
  offers: MembershipOffer[]; enabled: boolean; loading: boolean; busy: boolean;
  onPurchase: (offer: MembershipOffer) => void; onLoad: () => void;
  onRestore: () => void; onManage: () => void;
}) {
  const webUrl = process.env.EXPO_PUBLIC_WEB_URL?.replace(/\/$/, '');
  return <>
    <View className="flex-row flex-wrap gap-2 mt-4">
      {enabled && offers.length ? offers.map(offer => <Pressable key={offer.period} disabled={busy} onPress={() => onPurchase(offer)} className="flex-1 rounded-2xl border border-white/20 bg-white/10 px-4 py-3"><Text className="text-center text-xs font-semibold uppercase text-white">{offer.period} · {offer.priceLabel}</Text></Pressable>) : enabled ? <Pressable disabled={busy} onPress={onLoad} className="flex-1 rounded-2xl border border-white/20 bg-white/10 px-4 py-3"><Text className="text-center text-xs text-white">Load plans</Text></Pressable> : <Text className="text-xs text-white/50">{loading ? 'Checking plans…' : 'New purchases unavailable'}</Text>}
      <Pressable disabled={busy} onPress={onRestore} className="rounded-2xl border border-white/15 bg-white/5 px-4 py-3"><Text className="text-xs text-white/90">Restore Premium</Text></Pressable>
    </View>
    <Pressable onPress={onManage} className="mt-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3"><Text className="text-center text-xs text-white/80">Manage subscription</Text></Pressable>
    <Text className="mt-3 text-xs leading-5 text-white/55">Monthly and annual subscriptions renew automatically unless cancelled in your store account. No introductory trial. Deleting Aventi does not cancel your subscription.</Text>
    {webUrl ? <View className="mt-3 flex-row flex-wrap gap-4">{['privacy', 'terms', 'support'].map(path => <Pressable key={path} onPress={() => void Linking.openURL(`${webUrl}/${path}`)}><Text className="text-xs capitalize text-violet-300">{path}</Text></Pressable>)}</View> : null}
  </>;
}
