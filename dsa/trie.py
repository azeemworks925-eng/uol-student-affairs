"""
Trie (prefix tree), for prefix search.

How it works:
- Every node stands for one prefix. The root is the empty prefix; following the child for
  "a" then "l" then "i" reaches the node for "ali".
- Each node keeps its children in a small list of nodes (each child knows its character), and
  the values of the words that end exactly there.
- insert(word, value): walk down character by character, creating missing children, then
  store the value at the last node.
- starts_with(prefix): walk down the prefix. If a character is missing, nothing matches.
  Otherwise every word in the subtree below that node starts with the prefix, so collect their
  values with a depth-first search.
- Words are lowercased, so search is case-insensitive.

Complexity (L = word or prefix length, s = number of children of a node, at most the alphabet
size, m = nodes in the matching subtree, n = total characters inserted):
- insert: O(L * s): L steps, each scanning a node's child list.
- starts_with: O(L * s + m): walk the prefix, then visit the subtree once.
- space: O(n) nodes in the worst case (shared prefixes are stored once).
"""


class TrieNode:
    def __init__(self, character=""):
        self.character = character
        self.children = []  # TrieNode objects, one per next character
        self.values = []  # values of the words that end at this node

    def child(self, character):
        for node in self.children:
            if node.character == character:
                return node
        return None


class Trie:
    def __init__(self):
        self.root = TrieNode()
        self._words = 0

    def insert(self, word, value):
        node = self.root
        for character in word.lower():
            next_node = node.child(character)
            if next_node is None:
                next_node = TrieNode(character)
                node.children.append(next_node)
            node = next_node
        node.values.append(value)
        self._words += 1

    def starts_with(self, prefix):
        """Values of every inserted word that starts with `prefix` (an empty prefix matches all).
        A value inserted under several words can appear more than once."""
        node = self.root
        for character in prefix.lower():
            node = node.child(character)
            if node is None:
                return []
        found = []
        self._collect(node, found)
        return found

    def _collect(self, node, found):
        """Depth-first search: this node's values, then each child's subtree."""
        for value in node.values:
            found.append(value)
        for child in node.children:
            self._collect(child, found)

    def __len__(self):
        return self._words
