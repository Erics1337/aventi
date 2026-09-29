import * as Crypto from 'expo-crypto';
import { uuidV4FromBytes } from './uuid';

export function createSwipeActionId(): string {
  return uuidV4FromBytes(Crypto.getRandomBytes(16));
}
