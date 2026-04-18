/**
 * PostCard — community feed post with reaction buttons.
 * Reactions update optimistically via Feed.react().
 */
import { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Colors } from '../constants/colors';
import { Feed, PostItem } from '../lib/api';

interface Props {
  post:     PostItem;
  onPress?: () => void;
}

type Emoji = 'bull' | 'bear' | 'fire';

const EMOJIS: { key: Emoji; icon: string }[] = [
  { key: 'bull', icon: '🐂' },
  { key: 'bear', icon: '🐻' },
  { key: 'fire', icon: '🔥' },
];

const SIGNAL_COLORS: Record<string, string> = {
  bull:    Colors.bull,
  bear:    Colors.bear,
  neutral: Colors.textSecondary,
};

export default function PostCard({ post, onPress }: Props) {
  const [reactions,      setReactions]      = useState({ ...post.reactions });
  const [viewerReaction, setViewerReaction] = useState<string | null>(post.viewer_reaction);
  const [tapping,        setTapping]        = useState<string | null>(null);

  const handleReact = async (emoji: Emoji) => {
    setTapping(emoji);
    const prev       = { ...reactions };
    const prevViewer = viewerReaction;

    // Optimistic update
    const newReactions = { ...reactions };
    if (viewerReaction === emoji) {
      // Toggle off
      newReactions[emoji] = Math.max(0, newReactions[emoji] - 1);
      setViewerReaction(null);
    } else {
      if (viewerReaction && viewerReaction in newReactions) {
        newReactions[viewerReaction as Emoji] = Math.max(0, newReactions[viewerReaction as Emoji] - 1);
      }
      newReactions[emoji] += 1;
      setViewerReaction(emoji);
    }
    setReactions(newReactions);

    try {
      await Feed.react(post.id, emoji);
    } catch {
      // Revert on failure
      setReactions(prev);
      setViewerReaction(prevViewer);
    } finally {
      setTapping(null);
    }
  };

  const signalColor = post.signal_type ? SIGNAL_COLORS[post.signal_type] : null;
  const timeAgo = post.created_at ? _timeAgo(post.created_at) : '';

  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.9}>
      {/* User + meta row */}
      <View style={styles.meta}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {(post.user.display_name ?? 'P')[0].toUpperCase()}
          </Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.displayName}>{post.user.display_name}</Text>
          <Text style={styles.time}>{timeAgo}</Text>
        </View>
        {post.ticker && (
          <View style={styles.tickerBadge}>
            <Text style={styles.tickerBadgeText}>{post.ticker} {post.market ?? ''}</Text>
          </View>
        )}
        {post.signal_type && signalColor && (
          <View style={[styles.signalBadge, { borderColor: signalColor }]}>
            <Text style={[styles.signalBadgeText, { color: signalColor }]}>
              {post.signal_type.toUpperCase()}
            </Text>
          </View>
        )}
      </View>

      {/* Content */}
      <Text style={styles.content}>{post.content}</Text>

      {/* Reactions */}
      <View style={styles.reactions}>
        {EMOJIS.map(({ key, icon }) => (
          <TouchableOpacity
            key={key}
            style={[styles.reactionBtn, viewerReaction === key && styles.reactionActive]}
            onPress={() => handleReact(key)}
            disabled={!!tapping}
            activeOpacity={0.75}
          >
            <Text style={styles.reactionIcon}>{icon}</Text>
            <Text style={[styles.reactionCount, viewerReaction === key && styles.reactionCountActive]}>
              {reactions[key] > 0 ? reactions[key] : ''}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </TouchableOpacity>
  );
}

function _timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return '剛剛';
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

const styles = StyleSheet.create({
  card:               { backgroundColor: Colors.surface, borderRadius: 16, padding: 16, marginBottom: 10 },
  meta:               { flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 10 },
  avatar:             { width: 36, height: 36, borderRadius: 18, backgroundColor: Colors.elevated, justifyContent: 'center', alignItems: 'center' },
  avatarText:         { fontSize: 15, fontWeight: '700', color: Colors.gold },
  displayName:        { fontSize: 13, fontWeight: '700', color: Colors.textPrimary },
  time:               { fontSize: 11, color: Colors.textMuted, marginTop: 1 },
  tickerBadge:        { backgroundColor: Colors.elevated, borderRadius: 8, paddingHorizontal: 8, paddingVertical: 3 },
  tickerBadgeText:    { fontSize: 11, fontWeight: '700', color: Colors.textPrimary },
  signalBadge:        { borderWidth: 1, borderRadius: 8, paddingHorizontal: 7, paddingVertical: 2, marginLeft: 4 },
  signalBadgeText:    { fontSize: 10, fontWeight: '700' },
  content:            { fontSize: 14, color: Colors.textPrimary, lineHeight: 20, marginBottom: 12 },
  reactions:          { flexDirection: 'row', gap: 8 },
  reactionBtn:        { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 20, backgroundColor: Colors.elevated },
  reactionActive:     { backgroundColor: Colors.tabActive + '33' },
  reactionIcon:       { fontSize: 16 },
  reactionCount:      { fontSize: 12, color: Colors.textMuted, fontWeight: '600' },
  reactionCountActive:{ color: Colors.tabActive },
});
