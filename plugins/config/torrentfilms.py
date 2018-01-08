'''
Torrent Films Playlist Plugin configuration file
(C) Dorik1972
'''
# Insert your path to *.torrent files here
# In *nix based systems use '/path1/path2/path3' in windows 'C:\\path1\\path2\\path3'
directory = '/mnt/films'

# Background download playlist every N minutes to keep it always fresh =)
#
# 0 = disabled
updateevery = 0

# Output stream type
#
#streamtype = 'manifest.m3u8' # for HLS
streamtype = 'getstream' # for TS
