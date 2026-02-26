-- Aventi seed data (single-city sample)
insert into public.venues (id, name, slug, city, state, country, address, latitude, longitude)
values
  ('00000000-0000-0000-0000-000000000001', 'Aster Roof', 'aster-roof', 'Austin', 'TX', 'US', '123 Congress Ave', 30.2669, -97.7428),
  ('00000000-0000-0000-0000-000000000002', 'Southline Works', 'southline-works', 'Austin', 'TX', 'US', '400 E 4th St', 30.2655, -97.7394),
  ('00000000-0000-0000-0000-000000000003', 'The Quiet Room', 'the-quiet-room', 'Austin', 'TX', 'US', '905 W 10th St', 30.2748, -97.7531)
on conflict (id) do nothing;

insert into public.events (id, venue_id, title, description, category, booking_url, image_url, price_label, is_free)
values
  ('10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'Neon Terrace Session', 'Late-night rooftop set with city views.', 'nightlife', 'https://example.com/events/neon-terrace-session', 'https://images.unsplash.com/photo-1506157786151-b8491531f063?auto=format&fit=crop&w=1200&q=80', '$25', false),
  ('10000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000003', 'Candlelight Sound Bath', 'Guided reset with crystal bowls and tea.', 'wellness', 'https://example.com/events/candlelight-sound-bath', 'https://images.unsplash.com/photo-1506126613408-eca07ce68773?auto=format&fit=crop&w=1200&q=80', '$35', false),
  ('10000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000002', 'Warehouse Indie Night', 'Local bands and a vinyl afterparty.', 'concerts', 'https://example.com/events/warehouse-indie-night', 'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?auto=format&fit=crop&w=1200&q=80', '$18', false),
  ('10000000-0000-0000-0000-000000000004', '00000000-0000-0000-0000-000000000001', 'Midnight Velvet', 'Cocktail-forward lounge night with live sax.', 'nightlife', 'https://example.com/events/midnight-velvet', null, '$30', false),
  ('10000000-0000-0000-0000-000000000005', '00000000-0000-0000-0000-000000000002', 'Analog Dawn DJ Set', 'Sunrise-adjacent underground dance session.', 'concerts', 'https://example.com/events/analog-dawn', null, '$20', false)
on conflict (id) do nothing;

insert into public.event_occurrences (event_id, starts_at, ends_at)
values
  ('10000000-0000-0000-0000-000000000001', now() + interval '6 hours', now() + interval '10 hours'),
  ('10000000-0000-0000-0000-000000000002', now() + interval '18 hours', now() + interval '20 hours'),
  ('10000000-0000-0000-0000-000000000003', now() + interval '30 hours', now() + interval '34 hours'),
  ('10000000-0000-0000-0000-000000000004', now() + interval '48 hours', now() + interval '52 hours'),
  ('10000000-0000-0000-0000-000000000005', now() + interval '60 hours', now() + interval '64 hours')
on conflict do nothing;

insert into public.event_tags (event_id, tag, tag_type)
values
  ('10000000-0000-0000-0000-000000000001', 'energetic', 'vibe'),
  ('10000000-0000-0000-0000-000000000001', 'social', 'vibe'),
  ('10000000-0000-0000-0000-000000000001', 'late-night', 'vibe'),
  ('10000000-0000-0000-0000-000000000002', 'chill', 'vibe'),
  ('10000000-0000-0000-0000-000000000002', 'wellness', 'vibe'),
  ('10000000-0000-0000-0000-000000000003', 'live-music', 'vibe'),
  ('10000000-0000-0000-0000-000000000003', 'social', 'vibe'),
  ('10000000-0000-0000-0000-000000000004', 'luxury', 'vibe'),
  ('10000000-0000-0000-0000-000000000004', 'romantic', 'vibe'),
  ('10000000-0000-0000-0000-000000000005', 'energetic', 'vibe')
on conflict do nothing;
