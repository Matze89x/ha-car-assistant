-- the video choice is gone: Home shows media_id (photo or video), lists use photo_id (photo)
ALTER TABLE vehicles DROP COLUMN video_id;
