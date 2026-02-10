import random
import string

def generate_random_code(length=20):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def get_file_id(message):
    if message.document:
        return message.document.file_id, message.document.file_name, message.document.file_size, message.document.mime_type
    elif message.video:
        return message.video.file_id, message.video.file_name, message.video.file_size, message.video.mime_type
    elif message.audio:
        return message.audio.file_id, message.audio.file_name, message.audio.file_size, message.audio.mime_type
    elif message.photo:
        # Photos usually have multiple sizes, get the last one (best quality)
        return message.photo.file_id, "photo.jpg", message.photo.file_size, "image/jpeg"
    return None, None, None, None
