const { withAndroidManifest, AndroidConfig } = require('expo/config-plugins');

// Play may leave the app for bank verification. Preserve that purchase flow.
module.exports = function withPurchaseLaunchMode(config) {
  return withAndroidManifest(config, (next) => {
    const activity = AndroidConfig.Manifest.getMainActivityOrThrow(next.modResults);
    activity.$['android:launchMode'] = 'singleTop';
    return next;
  });
};
