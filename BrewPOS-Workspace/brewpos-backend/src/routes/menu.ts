import { Router } from 'express';
import { prisma } from '../db';
import multer from 'multer';
import path from 'path';
import fs from 'fs';

const router = Router();

// Ensure uploads directory exists
const uploadDir = path.join(__dirname, '../../public/uploads');
if (!fs.existsSync(uploadDir)) {
  fs.mkdirSync(uploadDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, uploadDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, uniqueSuffix + path.extname(file.originalname));
  }
});
const upload = multer({ storage });

// Get all menus
router.get('/', async (req, res) => {
  try {
    const itemQuantities = await prisma.transactionItem.groupBy({
      by: ['menuId'],
      _sum: {
        quantity: true
      }
    });
    
    const quantityMap = new Map(itemQuantities.map(item => [item.menuId, item._sum.quantity || 0]));

    const menus = await prisma.menu.findMany({
      include: { category: true },
    });
    
    const menusWithSoldCount = menus.map(menu => ({
      ...menu,
      soldCount: quantityMap.get(menu.id) || 0
    }));

    res.json(menusWithSoldCount);
  } catch (error) {
    res.status(500).json({ error: 'Failed to fetch menus' });
  }
});

// Create menu
router.post('/', upload.single('image'), async (req, res) => {
  try {
    const { name, description, price, categoryId } = req.body;
    let imageUrl = null;
    
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
    } else if (req.body.imageUrl) {
      imageUrl = req.body.imageUrl;
    }

    const menu = await prisma.menu.create({
      data: {
        name,
        description,
        price: Number(price),
        categoryId: Number(categoryId),
        imageUrl
      },
    });
    res.status(201).json(menu);
  } catch (error) {
    console.error('Error creating menu:', error);
    res.status(500).json({ error: 'Failed to create menu', details: error instanceof Error ? error.message : String(error) });
  }
});

// Update menu
router.put('/:id', upload.single('image'), async (req, res) => {
  try {
    const { id } = req.params;
    const { name, description, price, categoryId } = req.body;
    
    // Find existing menu to check current image if no new one provided
    const existingMenu = await prisma.menu.findUnique({ where: { id: Number(id) } });
    if (!existingMenu) {
      return res.status(404).json({ error: 'Menu not found' });
    }

    let imageUrl = existingMenu.imageUrl;
    if (req.file) {
      imageUrl = `/uploads/${req.file.filename}`;
    } else if (req.body.imageUrl !== undefined) {
      imageUrl = req.body.imageUrl;
    }

    const menu = await prisma.menu.update({
      where: { id: Number(id) },
      data: {
        name,
        description,
        price: Number(price),
        categoryId: Number(categoryId),
        imageUrl
      },
    });
    res.json(menu);
  } catch (error) {
    console.error('Error updating menu:', error);
    res.status(500).json({ error: 'Failed to update menu', details: error instanceof Error ? error.message : String(error) });
  }
});

export default router;
