import os
import sys
import glob
import re
from . import find_func as func
from statistics import median


def traversalDir_FirstDir(path):  
	ls = []  
	if os.path.exists(path):  
		for x in os.listdir(path):
			if os.path.isdir(os.path.join(path,x)):
				ls.append(x)
	return ls

# Determine if the source C file exists
# @name: name of object file
# @path: path of object file
def exists_source(name, path, kernel_path):
	p = path.split('build/')[1]
	path = os.path.join(os.path.join(kernel_path, p),name[:-1]+'c')
	if os.path.exists(path):
		return True
	return False


# Generate global function list
# @build_path:  build path
# @kernel_path: kernel path
def gen_global_list(build_path, kernel_path):
	print('pre-processing global functions...', file=sys.stderr)
	gdic = {}
	for roots,dirs,files in os.walk(build_path):
		for f in files:
			if re.match('^[^().]+\.o$',f):
				if not exists_source(f, roots, kernel_path):
					continue
				path = os.path.join(roots,f)
				print(path, file=sys.stderr)
				gdic = {**gdic, **find_global_func(path)}
	
	with open(os.path.join(OUTPUT_PATH,"global_funclist.txt"),"w") as f:
		ls = sorted([(x, gdic[x].path) for x in gdic], key=lambda x: x[1])
		for x in ls: print("%s %s"%(x[0], x[1]), file=f)

	return gdic


# Generate entry function list
# @build_path: build path
# @gdic: global function dictionary
# @output_path: output path
# @kernel_path: kernel path
# @rule: regular expression matching desired entry functions
def gen_entry_list(build_path, gdic, output_path, kernel_path, rule):
	print('finding entries...', file=sys.stderr)
	edic = {}
	for roots,dirs,files in os.walk(build_path):
		for f in files:
			if re.match('^[^().]+\.o$',f):
				if not exists_source(f, roots, kernel_path):
					continue
				path = os.path.join(roots,f)
				print(path, file=sys.stderr)
				edic = {**edic, **find_entry_func(path, gdic, rule)}

	with open(os.path.join(output_path,"entry_list.txt"),"w") as f:
		f.write('----------------entry func list----------------\n')
		for key in edic:
			print(key, edic[key].path, file=f)
		f.write('-----------------------end---------------------\n')

	return edic


# Print list
# @ls: target list
# @file_name: target file
def fprint_list(ls,file_name):
	with open(file_name,"w") as f:
		for x in ls:
			f.write("%s %s\n"%(x[0],x[1]))
	

# pre-process all global functions
def pre_process(build_path, output_path, kernel_path):
	# Create dir if not exist
	if not os.path.exists(output_path):
		os.mkdir(output_path)

	# Generate global function list if not exist
	if not os.path.exists(os.path.join(output_path,'global_funclist.txt')):
		global_dict = gen_global_list(build_path, kernel_path)
	# Or read from file to re-construct the dictionary
	else:
		global_dict = {}
		with open(os.path.join(output_path,'global_funclist.txt'), 'r') as f:
			print('processed global_funclist found', file=sys.stderr)
			cnt = 0
			for line in f:
				cnt += 1
				temp = line.split(' ')
				print(cnt, temp[0], file=sys.stderr)
				global_dict[temp[0]] = func.Func(temp[0],temp[1].strip(),None, None)
				
	# Add global attribution to those function
	for key in global_dict: global_dict[key].attr += ' global'
	return global_dict


# Find all global functions in kernel
# @path: build path
def find_global_func(path):
	func_dic = {}
	symtable, dump = objdump(path)
	if symtable is None or dump is None:
		return func_dic 

	symrule = re.compile("[\da-f]{8}\s([\s\S]{6}F)\s[^\s]+\s[\da-f]{8}\s([^\s]+)\n")

	# we assume global functions are unique
	name_ls = [x.group(2) for x in symrule.finditer(symtable) \
		if x.group(1)[0] == 'g' or x.group(1)[0] == 'u']
			
	for x in name_ls:
		func_dic[x] = func.Func(x, path, symtable, dump)
		
	return func_dic


# Find all entry functions in certain object file
# @path: target file path
# @gdic: global dictionary
# @rule: regular expression matching desired entry functions
def find_entry_func(path, gdic, rule):

	func_dic = {}
	# Dump it!
	symtable, dump = objdump(path)

	# If failed to dump, return
	if symtable is None or dump is None:
		return func_dic 

	# RE rule for suspend/resume entry
	# 	general symbol tabel paser
	symrule	 	= re.compile("[\da-f]{8}\s([\s\S]{6}F)\s[^\s]+\s[\da-f]{8}\s([^\s]+)\n")
	#	determine line is desired entry
	entryrule 	= re.compile(rule)

	# Find all valid entry name
	name_ls = set([x.group(2) for x in symrule.finditer(symtable)\
		if entryrule.match(x.group(2))])

	for x in name_ls: 
		if x in gdic:
			func_dic[x] = gdic[x]
		else:
			func_dic[x] = func.Func(x, path, symtable, dump) 

	return func_dic


# Dump object file
# @path: object file path
def objdump(path):
	
	if path[-2:] != ".o":
		print("error dumping file path:",path)
		return None, None
	dump_path, dump_name = os.path.split(path)
	dump_path = os.path.join(dump_path, dump_name[:-2] + '.dump')
	if not os.path.exists(dump_path):
		cmd = 'arm-linux-gnueabihf-objdump -D -t ' + path + ' > ' + dump_path
		os.system(cmd)
	f = open(dump_path,'r')
	if f is not None:
		dump = f.read()
		f.close()
		s1 = re.search("SYMBOL TABLE:",dump)
		s2 = re.search("Disassembly of section [^:]+:",dump)
		if s1 == None or s2 == None:
			print(path,file=sys.stderr)
			return None, None
		return dump[s1.end():s2.start()].strip()+'\n', dump[s2.end():].strip()+'\n'

	print("failed to dump file")
	return None, None


if __name__ == '__main__':

	global_dict = pre_process(BUILD_PATH, OUTPUT_PATH, KERNEL_PATH)

	function_dict = {}
	for d in traversalDir_FirstDir(DRIVER_PATH):
		path = os.path.join(OUTPUT_PATH, d)
		# If already fully searched, skip this
		if os.path.exists(os.path.join(path,"done.txt")):
			continue

		# Create dir if not exist
		if not os.path.exists(path):
			os.mkdir(path)

		# Generate entry dictionary
		entry_dict = gen_entry_list(os.path.join(DRIVER_PATH,d), global_dict, path, KERNEL_PATH)
		for key in entry_dict:
				entry_dict[key].attr += ' entry'

		# Generate call tree and print it!
		called_list = []
		with open(os.path.join(path,d+"_call_tree.txt"),"w") as f:
			for key in entry_dict:
				func.gen_call_tree(entry_dict[key], function_dict, global_dict, 0)
				print('______________________________________',file=f)
				print('entry function:\n%s: %s'%(key, entry_dict[key].attr),file=f)
				visited = []
				func.print_call_tree(entry_dict[key], 0, f, visited)
				print('______________________________________',file=f)
				# collect all visited functions
				called_list += visited
		# remove duplicated ones
		called_list = list(set(called_list))
		fprint_list(called_list, os.path.join(path, d+"_func_list.txt"))
		# Create done.txt indicate the folder is fully searched
		open(os.path.join(path,"done.txt"),"w")

