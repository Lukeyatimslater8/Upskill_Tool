import streamlit as st
import graphviz
import re
import docx  # Added the python-docx library

# --- 1. SETUP ---
st.set_page_config(layout="wide", page_title="Document Tree Explorer")


# --- 2. DOCX & PARSER ENGINES ---
def extract_text_from_docx(file):
    """
    Reads a Word document and converts its Native Headings into
    Markdown headers (#, ##) so our engine can read it.
    """
    doc = docx.Document(file)
    full_text = []

    for para in doc.paragraphs:
        style_name = para.style.name
        text = para.text.strip()

        if not text:
            continue

        # Check if the paragraph style is a standard Word Heading
        if style_name.startswith('Heading'):
            try:
                # Extract the heading level (e.g., "Heading 2" -> 2)
                level = int(style_name.split(' ')[1])
                full_text.append(f"{'#' * level} {text}")
            except ValueError:
                # Fallback if the style name is weird
                full_text.append(text)
        else:
            # Normal text
            full_text.append(text)

    return '\n'.join(full_text)


def parse_markdown_to_nodes(markdown_text):
    """
    Reads markdown text line by line. Uses headers (#, ##, ###) to create
    a nested dictionary tree of nodes automatically.
    """
    nodes = {"start": {"text": "## 📄 Document Root\nWelcome. Select a section to dive in:", "options": {}}}
    lines = markdown_text.split('\n')

    stack = {0: "start"}
    current_node_id = "start"

    for i, line in enumerate(lines):
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)

        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            node_id = f"node_{level}_{re.sub(r'[^a-zA-Z0-9]', '', title.lower())}_{i}"
            nodes[node_id] = {"text": f"{line}\n", "options": {}}

            parent_level = level - 1
            while parent_level > 0 and parent_level not in stack:
                parent_level -= 1

            parent_id = stack.get(parent_level, "start")
            nodes[parent_id]["options"][title] = node_id

            stack[level] = node_id
            current_node_id = node_id

            for l in list(stack.keys()):
                if l > level:
                    del stack[l]
        else:
            if line.strip():
                nodes[current_node_id]["text"] += line + "\n\n"

    return nodes


# --- 3. STATE MANAGEMENT ---
if 'current_node' not in st.session_state:
    st.session_state.current_node = 'start'
if 'history' not in st.session_state:
    st.session_state.history = []
if 'nodes' not in st.session_state:
    st.session_state.nodes = None


def navigate(next_node):
    st.session_state.history.append(st.session_state.current_node)
    st.session_state.current_node = next_node


def go_back():
    if st.session_state.history:
        st.session_state.current_node = st.session_state.history.pop()


def reset_app():
    st.session_state.current_node = 'start'
    st.session_state.history = []


# --- 4. THE VISUAL MAP ENGINE ---
def draw_forest_map(nodes, history, current):
    graph = graphviz.Digraph()
    graph.attr(rankdir='TB')

    for node_id, node_data in nodes.items():
        display_label = node_id.split('_')[2][:10] + "..." if len(node_id.split('_')) > 2 else node_id

        if node_id == current:
            graph.node(node_id, label=display_label, shape='doublecircle', style='filled', fillcolor='#ffcccc',
                       color='red')
        elif node_id in history:
            graph.node(node_id, label=display_label, shape='box', style='filled', fillcolor='#cce5ff', color='blue')
        else:
            graph.node(node_id, label="", shape='point', width='0.1')

    for node_id, node_data in nodes.items():
        for label, target_id in node_data['options'].items():
            if (node_id in history or node_id == current) and (target_id in history or target_id == current):
                graph.edge(node_id, target_id, color='blue')
            else:
                graph.edge(node_id, target_id, color='lightgrey')

    return graph


# --- 5. THE UI RENDERER ---
st.sidebar.title("📄 Upload Document")
st.sidebar.info("Upload a Word Doc (.docx), text, or markdown file to generate the tree.")

# Added 'docx' to the allowed types!
uploaded_file = st.sidebar.file_uploader("Choose a file", type=['txt', 'md', 'docx'])

if uploaded_file is not None:
    # Logic to handle different file types
    if uploaded_file.name.endswith('.docx'):
        text_content = extract_text_from_docx(uploaded_file)
    else:
        text_content = uploaded_file.getvalue().decode("utf-8")

    st.session_state.nodes = parse_markdown_to_nodes(text_content)
else:
    st.session_state.nodes = None

# Main Display Logic
if st.session_state.nodes is None:
    st.title("Welcome to the Doc Explorer!")
    st.write("⬅️ Please upload a Microsoft Word (`.docx`), Markdown (`.md`), or Text (`.txt`) file in the sidebar.")
    st.write(
        "*(**Note on Word Docs:** Ensure your document uses standard Word Heading styles like 'Heading 1', 'Heading 2', etc., for the tree to build correctly!)*")
else:
    nodes = st.session_state.nodes
    current_id = st.session_state.current_node
    node = nodes.get(current_id, nodes["start"])

    # A. Render the Visual Map
    with st.expander("🗺️ Show Forest Map (Click to Open)", expanded=False):
        st.caption("You are the Red Circle. Your path is Blue.")
        try:
            map_viz = draw_forest_map(nodes, st.session_state.history, current_id)
            st.graphviz_chart(map_viz)
        except Exception as e:
            st.error(f"Map Engine Error: {e}")

    # B. Render Main Content
    with st.container(border=True):
        col1, col2 = st.columns([1, 6])
        with col1:
            if st.session_state.history:
                if st.button("⬅️ Back"):
                    go_back()
                    st.rerun()
            if st.button("🏠 Home"):
                reset_app()
                st.rerun()

        st.markdown(node['text'])

        # C. Render Dynamic Option Buttons
        if node['options']:
            st.write("---")
            st.write("**Sub-sections available:**")

            max_cols = 4
            num_options = len(node['options'])
            cols = st.columns(min(num_options, max_cols))

            for idx, (label, next_id) in enumerate(node['options'].items()):
                col_idx = idx % max_cols
                if cols[col_idx].button(label, use_container_width=True, key=f"btn_{next_id}"):
                    navigate(next_id)
                    st.rerun()