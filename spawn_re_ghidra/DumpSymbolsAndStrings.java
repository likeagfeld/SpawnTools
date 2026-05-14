// Dump every named function + every defined string + every PVR/twiddle-like
// constant we can identify from the analyzed binary. Output is one JSON file
// per program at <output_dir>/<program_name>.json.
//
// Per-game RE pipeline expects:
//   - functions named pvr_LoadTexture* / pvr_load_texture* / pvr_load_tex*
//     (Katana SDK convention) → emit (address, name) so we can locate the
//     texture-load call sites in 1ST_READ.BIN.
//   - strings referencing texture filenames / patterns.
//   - dword constants that look like texture dimensions (256, 512, 1024)
//     in proximity to load calls.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;

public class DumpSymbolsAndStrings extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outDir = System.getProperty("dump.outDir");
        if (outDir == null) outDir = "D:/DC_CapcomTranslationTools/spawn_re_ghidra/ghidra_dumps";
        new File(outDir).mkdirs();
        File outFile = new File(outDir, currentProgram.getName() + ".json");
        PrintWriter w = new PrintWriter(new FileWriter(outFile));
        w.println("{");
        w.println("  \"program\": \"" + currentProgram.getName() + "\",");
        w.println("  \"image_base\": \"0x" + Long.toHexString(currentProgram.getImageBase().getOffset()) + "\",");

        // Functions
        w.println("  \"functions\": [");
        SymbolTable st = currentProgram.getSymbolTable();
        FunctionManager fm = currentProgram.getFunctionManager();
        boolean first = true;
        for (Function f : fm.getFunctions(true)) {
            String name = f.getName();
            // We care about FIDB-recovered names (anything not "FUN_XXXX")
            if (name.startsWith("FUN_")) continue;
            if (!first) w.println(",");
            first = false;
            w.print("    {\"addr\": \"0x" + Long.toHexString(f.getEntryPoint().getOffset()) +
                "\", \"name\": \"" + name.replace("\"", "\\\"") + "\"}");
        }
        w.println();
        w.println("  ],");

        // Strings (defined data of String type)
        w.println("  \"strings\": [");
        Listing listing = currentProgram.getListing();
        first = true;
        int strCount = 0;
        for (DataIterator it = listing.getDefinedData(true); it.hasNext(); ) {
            Data d = it.next();
            if (d == null) continue;
            String typeName = d.getDataType().getName();
            if (!typeName.contains("string") && !typeName.contains("char")) continue;
            String val = d.getDefaultValueRepresentation();
            if (val == null || val.length() < 4) continue;
            if (!first) w.println(",");
            first = false;
            w.print("    {\"addr\": \"0x" + Long.toHexString(d.getAddress().getOffset()) +
                "\", \"value\": " + jsonString(val) + "}");
            if (++strCount > 20000) break;
        }
        w.println();
        w.println("  ]");
        w.println("}");
        w.close();
        println("wrote " + outFile);
    }

    private String jsonString(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            if (c == '"') b.append("\\\"");
            else if (c == '\\') b.append("\\\\");
            else if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
            else b.append(c);
        }
        b.append("\"");
        return b.toString();
    }
}
