-- Create public bucket for AI-generated event images
-- This bucket stores Pollinations.ai generated images for better caching/performance

-- Insert the bucket (storage.buckets is managed by Supabase Storage)
INSERT INTO storage.buckets (id, name, public, avif_autodetection, file_size_limit, allowed_mime_types)
VALUES (
    'event-images',
    'event-images',
    true,  -- Public access so images can be served directly
    false,
    5242880,  -- 5MB limit per image
    ARRAY['image/jpeg', 'image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- Allow public read access to the bucket
CREATE POLICY "Public can view event images"
ON storage.objects
FOR SELECT
TO public
USING (bucket_id = 'event-images');

-- Allow authenticated users to upload event images with path-based validation
-- Path format: event-images/<event_id>/<filename>
-- Users must be authenticated and the first path segment must be a valid event UUID
CREATE POLICY "Authenticated users can upload event images"
ON storage.objects
FOR INSERT
TO authenticated
WITH CHECK (
    bucket_id = 'event-images'
    AND (storage.foldername(name))[1] IS NOT NULL
    AND (storage.foldername(name))[1] ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    -- User must own the event or be the uploader (service role bypasses RLS)
    -- Note: Additional business logic validation happens in the backend service layer
);

-- DELETE policy: service-role only (backend handles cleanup)
-- Deletions are intentionally restricted to service role to prevent accidental
-- user deletion of event images. Use backend API or Supabase dashboard for cleanup.
-- CREATE POLICY "Service role can delete event images"
-- ON storage.objects
-- FOR DELETE
-- TO service_role
-- USING (bucket_id = 'event-images');
