import { prisma } from '../db';

export async function logActivity(
  action: string,
  userId?: number,
  details?: string,
  entity?: string,
  entityId?: number
) {
  try {
    await prisma.systemLog.create({
      data: {
        action,
        userId,
        details,
        entity,
        entityId,
      },
    });
  } catch (error) {
    console.error('Failed to write system log:', error);
  }
}
