import { Platform } from 'react-native';
import type {
  CustomerInfo,
  PurchasesOffering,
  PurchasesPackage,
} from 'react-native-purchases';
import { aventiApi } from './api';
import { supabase } from './supabase';
import { createSerialOperations } from './serial-operations';

const billingOperation = createSerialOperations();

async function requireActiveAccount(userId: string) {
  const session = (await supabase?.auth.getSession())?.data.session;
  if (!session || session.user.id !== userId || session.user.is_anonymous) {
    throw new Error('Sign in to the owning permanent Aventi account to continue.');
  }
}

export type MembershipPeriod = 'monthly' | 'annual';

export interface MembershipOffer {
  period: MembershipPeriod;
  package: PurchasesPackage;
  priceLabel: string;
  title: string;
}

export interface MembershipOffering {
  identifier: string;
  offers: MembershipOffer[];
}

let configuredUserId: string | null = null;

function apiKey(): string | undefined {
  return Platform.OS === 'ios'
    ? process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY
    : process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY;
}

async function purchasesSdk() {
  const module = await import('react-native-purchases');
  return module.default;
}

export function isRevenueCatConfigured(): boolean {
  return Boolean(apiKey());
}

export function mapOffering(offering: PurchasesOffering | null): MembershipOffering | null {
  if (!offering) return null;
  const candidates: Array<[MembershipPeriod, PurchasesPackage | null]> = [
    ['monthly', offering.monthly],
    ['annual', offering.annual],
  ];
  const offers = candidates.flatMap(([period, productPackage]) =>
    productPackage
      ? [{ period, package: productPackage, priceLabel: productPackage.product.priceString, title: productPackage.product.title }]
      : [],
  );
  return offers.length > 0 ? { identifier: offering.identifier, offers } : null;
}

async function ensurePermanentIdentity(userId: string) {
  await requireActiveAccount(userId);
  if (!userId || userId.startsWith('$RCAnonymousID:')) {
    throw new Error('A permanent Aventi account is required for purchases.');
  }
  const key = apiKey();
  if (!key) {
    throw new Error('RevenueCat is not configured for this platform.');
  }
  const Purchases = await purchasesSdk();
  if (!configuredUserId) {
    Purchases.configure({ apiKey: key, appUserID: userId });
    configuredUserId = userId;
  } else if (configuredUserId !== userId || (await Purchases.getAppUserID()) !== userId) {
    await Purchases.logIn(userId);
    configuredUserId = userId;
  }
  const activeUserId = await Purchases.getAppUserID();
  if (activeUserId !== userId || activeUserId.startsWith('$RCAnonymousID:')) {
    throw new Error('RevenueCat could not verify your account identity.');
  }
  return Purchases;
}

async function reconcile(userId: string, info: CustomerInfo) {
  await requireActiveAccount(userId);
  return aventiApi.reconcileMembership({
    appUserId: userId,
    customerInfo: {
      originalAppUserId: info.originalAppUserId,
      activeEntitlementIds: Object.keys(info.entitlements.active),
      latestExpirationDate: info.latestExpirationDate,
      managementUrl: info.managementURL,
    },
  });
}

async function loadMembershipOfferingUnlocked(userId: string): Promise<MembershipOffering | null> {
  const Purchases = await ensurePermanentIdentity(userId);
  const [offerings, configured] = await Promise.all([Purchases.getOfferings(), aventiApi.getMembershipProducts()]);
  if (!configured.purchasesEnabled) return null;
  const offering = mapOffering(offerings.current);
  if (!offering) return null;
  offering.offers = offering.offers.filter(offer => configured.products.some(product => product.period === offer.period && product.productId === offer.package.product.identifier));
  return offering.offers.length ? offering : null;
}

async function purchaseMembershipUnlocked(userId: string, offer: MembershipOffer) {
  const Purchases = await ensurePermanentIdentity(userId);
  const configured = await aventiApi.getMembershipProducts();
  if (!configured.purchasesEnabled || !configured.products.some(product => product.period === offer.period && product.productId === offer.package.product.identifier)) {
    throw new Error('This subscription is not currently available.');
  }
  await requireActiveAccount(userId);
  if (await Purchases.getAppUserID() !== userId) throw new Error('Billing account changed. Try again.');
  try {
    const { customerInfo } = await Purchases.purchasePackage(offer.package);
    if (await Purchases.getAppUserID() !== userId) throw new Error('Billing account changed. Restore from the owning account.');
    return reconcile(userId, customerInfo);
  } catch (error) {
    const { PURCHASES_ERROR_CODE } = await import('react-native-purchases');
    const code = (error as { code?: string })?.code;
    if (code === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR) throw new Error('Purchase cancelled. Your plan is unchanged.');
    if (code === PURCHASES_ERROR_CODE.PAYMENT_PENDING_ERROR) throw new Error('Purchase pending store approval. Premium will activate after approval.');
    throw error;
  }
}

async function restoreMembershipUnlocked(userId: string) {
  const Purchases = await ensurePermanentIdentity(userId);
  const customerInfo = await Purchases.restorePurchases();
  if (await Purchases.getAppUserID() !== userId) throw new Error('Billing account changed. Restore from the owning account.');
  return reconcile(userId, customerInfo);
}

async function getMembershipManagementUrlUnlocked(userId: string): Promise<string | null> {
  const Purchases = await ensurePermanentIdentity(userId);
  return (await Purchases.getCustomerInfo()).managementURL;
}

export const loadMembershipOffering = (userId: string) =>
  billingOperation(() => loadMembershipOfferingUnlocked(userId));
export const purchaseMembership = (userId: string, offer: MembershipOffer) =>
  billingOperation(() => purchaseMembershipUnlocked(userId, offer));
export const restoreMembership = (userId: string) =>
  billingOperation(() => restoreMembershipUnlocked(userId));
export const getMembershipManagementUrl = (userId: string) =>
  billingOperation(() => getMembershipManagementUrlUnlocked(userId));
