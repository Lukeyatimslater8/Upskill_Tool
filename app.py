import streamlit as st
import graphviz
import re
import mammoth
import base64
import markdownify  # <-- NEW LIBRARY

# --- 1. SETUP ---
st.set_page_config(layout="wide", page_title="Document Tree Explorer")


# --- 2. DOCX & PARSER ENGINES ---
def extract_text_from_docx(file):
    """
    Uses Mammoth to convert a Word doc to HTML (which perfectly captures links),
    then uses Markdownify to turn it into clean Markdown for our engine.
    """

    def convert_image(image):
        with image.open() as image_bytes:
            encoded_src = base64.b64encode(image_bytes.read()).decode("ascii")
        return {
            "src": f"data:{image.content_type};base64,{encoded_src}"
        }

    # 1. Convert docx to HTML (Mammoth handles links natively in HTML)
    result = mammoth.convert_to_html(file, convert_image=mammoth.images.img_element(convert_image))
    html_content = result.value

    # 2. Convert that perfect HTML into clean Markdown
    md_text = markdownify.markdownify(html_content, heading_style="ATX")

    # 3. Clean up any rogue spaces inside bold tags that might break Streamlit
    def fix_bold_spacing(match):
        content = match.group(1)
        stripped = content.strip()
        leading = " " if content.startswith(" ") else ""
        trailing = " " if content.endswith(" ") else ""
        return f"{leading}**{stripped}**{trailing}"

    md_text = re.sub(r'\*\*(.*?)\*\*', fix_bold_spacing, md_text)
    md_text = re.sub(r'__(.*?)__', fix_bold_spacing, md_text)

    return md_text


def parse_markdown_to_nodes(markdown_text):
    """
    Reads markdown text line by line.
    1. Creates tree nodes from headers (#, ##).
    2. Sniffs out images, removes them from the text block, and saves them to the node's image gallery.
    3. Cleans HTML tags (like Word bookmarks) from header titles and displayed text.
    """
    nodes = {
        "start": {"text": "## 📄 Document Root\nWelcome. Select a section to dive in:", "options": {}, "images": []}}
    lines = markdown_text.split('\n')

    stack = {0: "start"}
    current_node_id = "start"

    for i, line in enumerate(lines):
        # Find any markdown images on this line: ![alt_text](image_url_or_base64)
        images_found = re.findall(r'!\[.*?\]\((.*?)\)', line)

        # Strip the image code out of the text line so it doesn't render inline
        clean_line = re.sub(r'!\[.*?\]\((.*?)\)', '', line)

        # Look for headers
        heading_match = re.match(r'^(#{1,6})\s+(.*)', clean_line)

        if heading_match:
            level = len(heading_match.group(1))
            raw_title = heading_match.group(2).strip()

            # Scrub any HTML tags (like <a>) out of the title
            clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()

            node_id = f"node_{level}_{re.sub(r'[^a-zA-Z0-9]', '', clean_title.lower())}_{i}"

            # --- THE FIX: Reconstruct the header using the clean_title ---
            clean_header = f"{'#' * level} {clean_title}"
            nodes[node_id] = {"text": f"{clean_header}\n", "options": {}, "images": []}

            if images_found:
                nodes[node_id]["images"].extend(images_found)

            parent_level = level - 1
            while parent_level > 0 and parent_level not in stack:
                parent_level -= 1

            parent_id = stack.get(parent_level, "start")

            nodes[parent_id]["options"][clean_title] = node_id

            stack[level] = node_id
            current_node_id = node_id

            for l in list(stack.keys()):
                if l > level:
                    del stack[l]
        else:
            if clean_line.strip() or images_found:
                nodes[current_node_id]["text"] += clean_line + "\n"
                if images_found:
                    nodes[current_node_id].setdefault("images", []).extend(images_found)

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

uploaded_file = st.sidebar.file_uploader("Choose a file", type=['txt', 'md', 'docx'])

if uploaded_file is not None:
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

        # Check if we have images to determine the layout
        has_images = bool(node.get('images'))

        if has_images:
            # 3-Column Layout: Nav (1), Text (3), Images (4)
            cols = st.columns([1, 3, 4])
        else:
            # 2-Column Layout: Nav (1), Text spans the rest (7)
            cols = st.columns([1, 7])

        # 1. Render Navigation (Always the first column)
        with cols[0]:
            if st.session_state.history:
                if st.button("⬅️ Back", use_container_width=True):
                    go_back()
                    st.rerun()
            if st.button("🏠 Home", use_container_width=True):
                reset_app()
                st.rerun()

        # 2. Render Text Content (Always the second column)
        with cols[1]:
            st.markdown(node['text'])

            # Path option buttons explicitly sit at the bottom of the text column
            if node['options']:
                st.write("---")
                st.write("**Sub-sections available:**")

                # Dynamic button columns: 4 wide if no image, 2 wide if compressed by an image
                max_cols = 2 if has_images else 4
                num_options = len(node['options'])
                btn_cols = st.columns(min(num_options, max_cols) if num_options > 0 else 1)

                for idx, (label, next_id) in enumerate(node['options'].items()):
                    col_idx = idx % max_cols
                    if btn_cols[col_idx].button(label, use_container_width=True, key=f"btn_{next_id}"):
                        navigate(next_id)
                        st.rerun()

        # 3. Render Images (Only if they exist, in the third column)
        if has_images:
            with cols[2]:
                for img_data in node['images']:
                    st.image(img_data, use_container_width=True)
